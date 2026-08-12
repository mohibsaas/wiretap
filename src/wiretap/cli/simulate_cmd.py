"""wiretap simulate — execute scenario simulations against a live agent."""

from __future__ import annotations

import asyncio

import typer
from rich import print


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
        agent_id: str | None = typer.Option(
            None,
            "--agent-id",
            help="Override suite agent_id (run this suite against a different agent).",
        ),
        platform: str | None = typer.Option(
            None, "--platform", help="Override suite platform (retell|vapi|bland|custom)."
        ),
        token_env: str | None = typer.Option(
            None, "--token-env", help="Override env var name for the platform API key."
        ),
        agent_from: str | None = typer.Option(
            None,
            "--agent-from",
            help="Copy agent target from another local suite, then apply other overrides.",
        ),
    ) -> None:
        """Simulate scenarios against the configured live agent.

        Suites embed a default agent. Use --agent-id / --platform / --agent-from
        to reuse the same test suite against a different live agent.
        """
        from wiretap.agent import simulate_scenario
        from wiretap.paths import suite_path
        from wiretap.suite import load_suite
        from wiretap.suite.agent_override import with_agent_override
        from wiretap.suite.evaluations import save_evaluation_run
        import uuid
        from datetime import UTC, datetime

        path = suite_path(suite)
        cfg = load_suite(path)
        cfg = with_agent_override(
            cfg,
            agent_id=agent_id,
            platform=platform,
            token_env=token_env,
            agent_from=agent_from,
        )
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

        async def _simulate_all():
            sem = asyncio.Semaphore(concurrency)

            async def one(sc):
                async with sem:
                    return await simulate_scenario(
                        cfg, sc, suite_id=suite_id, batch_id=batch_id
                    )

            return await asyncio.gather(*[one(sc) for sc in selected])

        target = cfg.agent.agent_id or cfg.agent.platform or "local"
        print(f"[cyan]Suite[/cyan] {path}  [cyan]agent[/cyan] {target}")
        print(f"[cyan]Evaluation[/cyan] {batch_id}")
        artifacts = asyncio.run(_simulate_all())
        failures = 0
        for art in artifacts:
            title = art.scenario_name or art.scenario_id
            if art.meta.get("inconclusive"):
                print(
                    f"  [yellow]INCONCLUSIVE[/yellow]  {title} — {art.judge.reason[:140]}"
                )
                continue
            status = "[green]PASS[/green]" if art.passed else "[red]FAIL[/red]"
            print(f"  {status}  {title} — {art.judge.reason[:140]}")
            if not art.passed:
                failures += 1
                for f in art.rules.failures:
                    print(f"    rule: {f}")
                for s in art.judge.suggestions:
                    print(f"    • {s}")

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
                "failed": failures,
                "inconclusive": inconclusive,
                "total": len(selected),
                "concurrency": concurrency,
            }
        )

        raise typer.Exit(code=1 if failures else 0)
