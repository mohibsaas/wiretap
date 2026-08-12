"""wiretap report."""

from __future__ import annotations

import typer
from rich import print

from wiretap.suite import iter_simulations


def register(app: typer.Typer) -> None:
    @app.command("report")
    def report_cmd(
        limit: int = typer.Option(20, "--limit", "-n", help="Max simulations to show."),
    ) -> None:
        """Show recent simulations; suggestions appear on failures only."""
        sims = iter_simulations(limit=limit)
        if not sims:
            print(
                "No simulations yet. Use [bold]wiretap simulate --all[/bold] first."
            )
            raise typer.Exit(0)
        for art in sims:
            status = "PASS" if art.passed else "FAIL"
            title = art.scenario_name or art.scenario_id
            print(
                f"[{status}] {art.suite_id}/{title} — {art.judge.reason[:160]}"
            )
            if not art.passed and art.judge.suggestions:
                for s in art.judge.suggestions:
                    print(f"  • {s}")
