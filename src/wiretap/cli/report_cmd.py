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
        from wiretap.cli import style as ui

        with ui.spinner("Loading simulations…"):
            sims = iter_simulations(limit=limit)
        if not sims:
            print(
                "No simulations yet. Use [bold]wiretap simulate --all[/bold] first."
            )
            raise typer.Exit(0)
        for art in sims:
            if art.meta.get("inconclusive"):
                status = "INCONCLUSIVE"
            elif art.passed:
                status = "PASS"
            elif (art.judge.verdict or "").lower() == "partial":
                status = "PARTIAL"
            else:
                status = "FAIL"
            title = art.scenario_name or art.scenario_id
            pct = ""
            if art.judge.score is not None and status != "INCONCLUSIVE":
                pct = f"{round(float(art.judge.score) * 100)}% · "
            print(
                f"[{status}] {art.suite_id}/{title} — {pct}{art.judge.reason[:140]}"
            )
            if not art.passed and art.judge.suggestions:
                for s in art.judge.suggestions:
                    print(f"  • {s}")
