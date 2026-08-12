"""Create a starter suite in .wiretap/suites/."""

from __future__ import annotations

import typer
from rich import print

from wiretap.config import DEFAULT_SUITE
from wiretap.paths import ensure_layout, suite_path


def register(app: typer.Typer) -> None:
    @app.command("init")
    def init_cmd(
        name: str = typer.Option("default", "--name", help="Suite name under .wiretap/suites/."),
        force: bool = typer.Option(False, "--force", help="Overwrite if the suite exists."),
    ) -> None:
        """Create a starter suite in .wiretap/suites/."""
        ensure_layout()
        path = suite_path(name)
        if path.exists() and not force:
            print(f"[yellow]Already exists:[/yellow] {path} (use --force to overwrite)")
            raise typer.Exit(1)
        path.write_text(DEFAULT_SUITE, encoding="utf-8")
        print(f"[green]Wrote[/green] {path}")
        print(
            "Set LLM keys in the environment (see .env.example), then: "
            "[bold]wiretap simulate --all[/bold]"
        )
