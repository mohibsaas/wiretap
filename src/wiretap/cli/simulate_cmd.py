"""wiretap simulate — execute scenario simulations against a live agent."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import typer
from rich import print
from rich.console import Console

# Voice dials are slow; don't let one hung scenario block forever.
DEFAULT_SCENARIO_TIMEOUT_S = 240.0


def register(app: typer.Typer) -> None:
    @app.command("simulate")
    def simulate_cmd(
        suite: str = typer.Option(
            "default",
            "--suite",
            "-s",
            help="Suite name or YAML path (default: onboard suite, or the only local suite).",
        ),
        all_scenarios: bool = typer.Option(
            False, "--all", help="Simulate every scenario."
        ),
        scenario_id: str | None = typer.Option(
            None, "--scenario", help="Simulate one scenario id."
        ),
        concurrency: int = typer.Option(
            1, "--concurrency", "-c", min=1, help="Parallel simulations."
        ),
        force_concurrency: bool = typer.Option(
            False,
            "--force-concurrency",
            help="Do not clamp concurrency to the provider-safe live-dial cap.",
        ),
        pass_threshold: float = typer.Option(
            0.7,
            "--pass-threshold",
            min=0.0,
            max=1.0,
            help=(
                "Goal-match pass bar (default 0.7 = 70%). "
                "Scores below suite fail_below (default 50%) fail; "
                "between fail_below and this value are PARTIAL."
            ),
        ),
        strict: bool = typer.Option(
            False, "--strict", help="Strict caller mode (low temp + contract checks)."
        ),
        quiet: bool = typer.Option(
            False, "--quiet", "-q", help="Minimal output (no live progress board)."
        ),
        no_advice: bool = typer.Option(
            False,
            "--no-advice",
            help="Skip the run-level agent-improvement advisor (one LLM call).",
        ),
        agent_id: str | None = typer.Option(
            None,
            "--agent-id",
            help="Override suite agent_id (run this suite against a different agent).",
        ),
        platform: str | None = typer.Option(
            None,
            "--platform",
            help="Override suite platform (retell|vapi|elevenlabs|livekit|…).",
        ),
        token_env: str | None = typer.Option(
            None, "--token-env", help="Override env var name for the platform API key."
        ),
        agent_from: str | None = typer.Option(
            None,
            "--agent-from",
            help="Copy agent target from another local suite, then apply other overrides.",
        ),
        transport: str | None = typer.Option(
            None,
            "--transport",
            help="How to reach the agent: web or phone (skips the prompt).",
        ),
        phone: str | None = typer.Option(
            None,
            "--phone",
            help="Agent phone number to dial, E.164 (skips the picker).",
        ),
        from_number: str | None = typer.Option(
            None,
            "--from-number",
            help="Twilio caller number to dial from (skips the picker).",
        ),
        timeout: float = typer.Option(
            DEFAULT_SCENARIO_TIMEOUT_S,
            "--timeout",
            min=30.0,
            help="Per-scenario timeout in seconds.",
        ),
    ) -> None:
        """Simulate scenarios against the configured live agent.

        Suites embed a default agent. Use --agent-id / --platform / --agent-from
        to reuse the same test suite against a different live agent.
        """
        from wiretap.agent import simulate_scenario
        from wiretap.agent.events import SimEvent
        from wiretap.cli.prompts import (
            choose_transport,
            ensure_agent_number,
            ensure_caller_configured,
            ensure_platform_key,
            ensure_pstn_configured,
            require_pstn_extra,
        )
        from wiretap.cli.sim_display import (
            SimulateDisplay,
            print_fail_details,
            print_inconclusive_details,
            print_run_advice,
            print_run_summary,
        )
        from wiretap.eval.advisor import advise_for_run
        from wiretap.paths import resolve_suite_path
        from wiretap.suite import load_suite
        from wiretap.suite.agent_override import with_agent_override
        from wiretap.suite.evaluations import save_evaluation_run

        # Test agent (LLM/STT/TTS) before dialing
        ensure_caller_configured()

        from wiretap.cli import style as ui

        try:
            with ui.spinner(f"Loading suite {suite}…"):
                path = resolve_suite_path(suite)
                cfg = load_suite(path)
                from wiretap.services.onboard import apply_simulator_config

                cfg = apply_simulator_config(cfg)
                cfg = with_agent_override(
                    cfg,
                    agent_id=agent_id,
                    platform=platform,
                    token_env=token_env,
                    agent_from=agent_from,
                )
        except FileNotFoundError as exc:
            ui.err(str(exc))
            raise typer.Exit(1) from None
        if suite not in {path.stem, str(path)} and suite == "default":
            ui.muted(f"Using suite [bold]{path.stem}[/bold]")
        # Platform key for live dial (skip for custom/text stub)
        plat = (cfg.agent.platform or "").lower().strip()
        if plat:
            ensure_platform_key(plat)
        # Web or phone is decided per run, so the suite stays untouched.
        # PSTN still needs the platform key above — post-call artifacts come
        # from the platform, not from Twilio.
        chosen = choose_transport(cfg, transport=transport)
        if chosen == "pstn":
            require_pstn_extra()
            cfg = with_agent_override(
                cfg,
                transport="pstn",
                phone_number=ensure_agent_number(cfg, phone=phone),
            )
            ensure_pstn_configured(from_number=from_number)
        elif chosen != cfg.agent.transport.value:
            cfg = with_agent_override(cfg, transport=chosen)
        if strict:
            cfg.mode.strict = True
            cfg.mode.temperature = 0.2
        suite_id = path.stem
        batch_id = uuid.uuid4().hex
        started = (
            datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )

        selected = cfg.scenarios
        if scenario_id:
            selected = [s for s in cfg.scenarios if s.id == scenario_id]
            if not selected:
                print(f"[red]No scenario[/red] {scenario_id!r}")
                raise typer.Exit(1)
        elif not all_scenarios and len(cfg.scenarios) > 1:
            print("Pass [bold]--all[/bold] or [bold]--scenario ID[/bold].")
            raise typer.Exit(1)

        # Live voice: clamp to provider-safe parallel dials unless forced.
        from wiretap.eval.concurrency import resolve_concurrency

        conc, conc_note = resolve_concurrency(
            concurrency,
            transport=cfg.agent.transport.value,
            platform=cfg.agent.platform,
            force=force_concurrency,
        )
        if conc_note:
            print(f"[yellow]Note[/yellow] {conc_note}")

        target = cfg.agent.agent_id or cfg.agent.platform or "local"
        plat = cfg.agent.platform or "local"
        console = Console(stderr=False)

        display: SimulateDisplay | None = None
        if not quiet:
            display = SimulateDisplay(
                suite_label=path.name,
                agent_label=str(target),
                platform=str(plat),
                batch_id=batch_id,
                total=len(selected),
                concurrency=conc,
                console=console,
            )
            for sc in selected:
                display.add_scenario(sc.id, sc.name or sc.id)
        else:
            print(f"[cyan]Suite[/cyan] {path}  [cyan]agent[/cyan] {target}")
            print(f"[cyan]Evaluation[/cyan] {batch_id}  [cyan]concurrency[/cyan] {conc}")

        def on_progress(event: SimEvent) -> None:
            if display is not None:
                display.on_event(event)

        async def _simulate_all():
            sem = asyncio.Semaphore(conc)
            results = []

            async def one(sc):
                title = sc.name or sc.id
                on_progress(
                    SimEvent(
                        phase="queued",
                        scenario_id=sc.id,
                        scenario_name=title,
                        detail="waiting for slot",
                    )
                )
                async with sem:
                    try:
                        art = await asyncio.wait_for(
                            simulate_scenario(
                                cfg,
                                sc,
                                suite_id=suite_id,
                                batch_id=batch_id,
                                on_progress=on_progress,
                                pass_threshold=pass_threshold,
                            ),
                            timeout=timeout,
                        )
                        return art
                    except TimeoutError:
                        on_progress(
                            SimEvent(
                                phase="failed",
                                scenario_id=sc.id,
                                scenario_name=title,
                                detail=f"Timed out after {int(timeout)}s",
                            )
                        )
                        return None
                    except (RuntimeError, OSError, ValueError, KeyError) as exc:
                        on_progress(
                            SimEvent(
                                phase="failed",
                                scenario_id=sc.id,
                                scenario_name=title,
                                detail=str(exc)[:200],
                            )
                        )
                        return None
                    except Exception as exc:  # noqa: BLE001 — isolate unknown transport/LLM errors
                        on_progress(
                            SimEvent(
                                phase="failed",
                                scenario_id=sc.id,
                                scenario_name=title,
                                detail=str(exc)[:200],
                            )
                        )
                        return None

            gathered = await asyncio.gather(*[one(sc) for sc in selected])
            for item in gathered:
                if item is not None:
                    results.append(item)
            return results

        if display is not None:
            try:
                with display:
                    artifacts = asyncio.run(_simulate_all())
            except KeyboardInterrupt:
                print("\n[yellow]Interrupted — disconnecting LiveKit sessions…[/yellow]")
                raise SystemExit(130) from None
        else:
            try:
                artifacts = asyncio.run(_simulate_all())
            except KeyboardInterrupt:
                print("\nInterrupted — disconnecting…")
                raise SystemExit(130) from None

        failures = 0
        partials = 0
        errors = len(selected) - len(artifacts)

        # Quiet mode (or post-summary for failures with suggestions)
        if quiet:
            for art in artifacts:
                title = art.scenario_name or art.scenario_id
                if art.meta.get("inconclusive"):
                    print_inconclusive_details(art, console=console)
                    continue
                if art.passed:
                    print(f"  [green]PASS[/green]  {title} — {art.judge.reason[:140]}")
                    continue
                if (art.judge.verdict or "").lower() == "partial":
                    partials += 1
                else:
                    failures += 1
                print_fail_details(art, console=console)
        else:
            # Live board already shows PASS/FAIL/PARTIAL; print detail cards.
            detail_arts = [
                a
                for a in artifacts
                if not a.meta.get("inconclusive") and not a.passed
            ]
            incon_arts = [a for a in artifacts if a.meta.get("inconclusive")]
            if detail_arts or incon_arts:
                console.print()
                from wiretap.cli.style import ACCENT, MUTED
                from rich.text import Text as RichText

                n_partial = sum(
                    1
                    for a in detail_arts
                    if (a.judge.verdict or "").lower() == "partial"
                )
                n_fail = len(detail_arts) - n_partial
                label = RichText()
                label.append("◈ ", style=f"bold {ACCENT}")
                label.append("Result details", style=f"bold {ACCENT}")
                if n_fail:
                    label.append(f"  ·  {n_fail} fail", style=MUTED)
                if n_partial:
                    label.append(f"  ·  {n_partial} partial", style=MUTED)
                if incon_arts:
                    label.append(
                        f"  ·  {len(incon_arts)} inconclusive",
                        style=MUTED,
                    )
                console.print(label)
                console.print()
            for art in incon_arts:
                print_inconclusive_details(art, console=console)
            for art in detail_arts:
                if (art.judge.verdict or "").lower() == "partial":
                    partials += 1
                else:
                    failures += 1
                print_fail_details(art, console=console)

        advice = None
        if artifacts and not no_advice:
            try:
                advice = asyncio.run(advise_for_run(cfg, artifacts, suite_id=suite_id))
            except Exception:  # noqa: BLE001 — advice never changes the outcome
                advice = None

        passed = sum(
            1 for a in artifacts if a.passed and not a.meta.get("inconclusive")
        )
        inconclusive = sum(1 for a in artifacts if a.meta.get("inconclusive"))
        finished = (
            datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        save_evaluation_run(
            {
                "batch_id": batch_id,
                "suite_id": suite_id,
                "created_at": started,
                "finished_at": finished,
                "status": "completed",
                "scenario_ids": [s.id for s in selected],
                "simulation_ids": [a.simulation_id for a in artifacts],
                "passed": passed,
                "failed": failures + errors,
                "partial": partials,
                "inconclusive": inconclusive,
                "total": len(selected),
                "concurrency": conc,
                "pass_threshold": pass_threshold,
                "advice": advice.model_dump(mode="json") if advice else None,
            }
        )

        if advice:
            print_run_advice(advice, console=console)

        print_run_summary(
            passed=passed,
            failed=failures + errors,
            partial=partials,
            inconclusive=inconclusive,
            total=len(selected),
            batch_id=batch_id,
            console=console,
        )

        raise typer.Exit(code=1 if (failures + errors + partials) else 0)
