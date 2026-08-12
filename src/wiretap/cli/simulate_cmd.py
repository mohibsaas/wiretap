"""wiretap simulate — execute scenario simulations against a live agent."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich import print

from wiretap.config import load_suite
from wiretap.paths import suite_path
from wiretap.report import write_json_report, write_junit_report
from wiretap.runner import simulate_scenario


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
        junit: Path | None = typer.Option(
            None, "--junit", help="Write JUnit XML report to this path."
        ),
        json_out: Path | None = typer.Option(
            None, "--json", help="Write JSON report to this path."
        ),
        strict: bool = typer.Option(
            False, "--strict", help="Strict caller mode (low temp + contract checks)."
        ),
    ) -> None:
        """Simulate scenarios against the configured live agent."""
        path = suite_path(suite)
        cfg = load_suite(path)
        if strict:
            cfg.mode.strict = True
            cfg.mode.temperature = 0.2
        suite_id = path.stem

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
                    return await simulate_scenario(cfg, sc, suite_id=suite_id)

            return await asyncio.gather(*[one(sc) for sc in selected])

        print(f"[cyan]Suite[/cyan] {path}")
        artifacts = asyncio.run(_simulate_all())
        failures = 0
        for art in artifacts:
            if art.meta.get("inconclusive"):
                print(
                    f"  [yellow]INCONCLUSIVE[/yellow]  {art.scenario_id} — {art.judge.reason[:140]}"
                )
                continue
            status = "[green]PASS[/green]" if art.passed else "[red]FAIL[/red]"
            print(f"  {status}  {art.scenario_id} — {art.judge.reason[:140]}")
            if not art.passed:
                failures += 1
                for f in art.rules.failures:
                    print(f"    rule: {f}")
                for s in art.judge.suggestions:
                    print(f"    • {s}")

        if junit:
            write_junit_report(artifacts, junit, suite_name=suite_id)
            print(f"[green]JUnit[/green] {junit}")
        if json_out:
            write_json_report(artifacts, json_out)
            print(f"[green]JSON[/green] {json_out}")

        raise typer.Exit(code=1 if failures else 0)
