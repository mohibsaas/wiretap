"""wiretap simulate — execute scenario simulations against a live agent."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import typer
from rich import print
from rich.console import Console

# Voice dials are slow; don't let one hung scenario block forever.
DEFAULT_SCENARIO_TIMEOUT_S = 180.0


def register(app: typer.Typer) -> None:
    @app.command("simulate")
    def simulate_cmd(
        suite: str = typer.Option(
            "default", "--suite", "-s", help="Suite name or YAML path."
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
        strict: bool = typer.Option(
            False, "--strict", help="Strict caller mode (low temp + contract checks)."
        ),
        quiet: bool = typer.Option(
            False, "--quiet", "-q", help="Minimal output (no live progress board)."
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
        from wiretap.cli.prompts import ensure_caller_configured, ensure_platform_key
        from wiretap.cli.sim_display import SimulateDisplay
        from wiretap.paths import suite_path
        from wiretap.suite import load_suite
        from wiretap.suite.agent_override import with_agent_override
        from wiretap.suite.evaluations import save_evaluation_run

        # Test agent (LLM/STT/TTS) before dialing
        ensure_caller_configured()

        from wiretap.cli import style as ui

        with ui.spinner(f"Loading suite {suite}…"):
            path = suite_path(suite)
            cfg = load_suite(path)
            cfg = with_agent_override(
                cfg,
                agent_id=agent_id,
                platform=platform,
                token_env=token_env,
                agent_from=agent_from,
            )
        # Platform key for live dial (skip for custom/text stub)
        plat = (cfg.agent.platform or "").lower().strip()
        if plat:
            ensure_platform_key(plat)
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

        # Live voice: keep concurrency low to avoid slamming providers.
        conc = max(1, concurrency)
        if cfg.agent.transport.value != "text":
            conc = min(conc, 2)

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
                console=console,
            )
            for sc in selected:
                display.add_scenario(sc.id, sc.name or sc.id)
        else:
            print(f"[cyan]Suite[/cyan] {path}  [cyan]agent[/cyan] {target}")
            print(f"[cyan]Evaluation[/cyan] {batch_id}")

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
            with display:
                artifacts = asyncio.run(_simulate_all())
        else:
            artifacts = asyncio.run(_simulate_all())

        failures = 0
        errors = len(selected) - len(artifacts)

        # Quiet mode (or post-summary for failures with suggestions)
        if quiet:
            for art in artifacts:
                title = art.scenario_name or art.scenario_id
                if art.meta.get("inconclusive"):
                    print(
                        f"  [yellow]INCONCLUSIVE[/yellow]  {title} — "
                        f"{art.judge.reason[:140]}"
                    )
                    continue
                status = "[green]PASS[/green]" if art.passed else "[red]FAIL[/red]"
                print(f"  {status}  {title} — {art.judge.reason[:140]}")
                if not art.passed:
                    failures += 1
                    for f in art.rules.failures:
                        print(f"    rule: {f}")
                    tools = ui.tool_summary(art)
                    if tools:
                        print(f"    {tools}")
                    for s in art.judge.suggestions:
                        print(f"    • {s}")
        else:
            # Live board already shows PASS/FAIL; print suggestion details for fails.
            for art in artifacts:
                if art.meta.get("inconclusive"):
                    continue
                if not art.passed:
                    failures += 1
                    title = art.scenario_name or art.scenario_id
                    tools = ui.tool_summary(art)
                    if art.rules.failures or art.judge.suggestions or tools:
                        print(f"[bold red]Fail details[/bold red] · {title}")
                        for f in art.rules.failures:
                            print(f"  rule: {f}")
                        if tools:
                            print(f"  {tools}")
                        for s in art.judge.suggestions:
                            print(f"  • {s}")

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
                "inconclusive": inconclusive,
                "total": len(selected),
                "concurrency": conc,
            }
        )

        print(
            f"[bold]Done[/bold]  "
            f"[green]{passed} pass[/green] · "
            f"[red]{failures + errors} fail[/red] · "
            f"[yellow]{inconclusive} inconclusive[/yellow]  "
            f"({len(selected)} total)  ·  evaluation [cyan]{batch_id}[/cyan]"
        )

        raise typer.Exit(code=1 if (failures + errors) else 0)
