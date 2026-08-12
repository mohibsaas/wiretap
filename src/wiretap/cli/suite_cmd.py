"""suite list | show | path."""

from __future__ import annotations

import typer
from rich import print

from wiretap.paths import suite_path, suites_dir


def register(app: typer.Typer) -> None:
    suite_app = typer.Typer(
        no_args_is_help=True,
        help="Manage local suites under .wiretap/suites/.",
    )
    app.add_typer(suite_app, name="suite")

    @suite_app.command("list")
    def suite_list() -> None:
        """List local suites."""
        d = suites_dir()
        if not d.is_dir():
            print("No suites yet. Run [bold]wiretap init[/bold].")
            raise typer.Exit(0)
        files = sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml"))
        if not files:
            print("No suites yet. Run [bold]wiretap init[/bold].")
            raise typer.Exit(0)
        for f in files:
            print(f.stem)

    @suite_app.command("path")
    def suite_path_cmd(name: str = typer.Argument("default")) -> None:
        """Print the filesystem path for a suite."""
        print(suite_path(name))

    @suite_app.command("show")
    def suite_show(name: str = typer.Argument("default")) -> None:
        """Print suite YAML."""
        path = suite_path(name)
        if not path.is_file():
            print(f"[red]Not found:[/red] {path}")
            raise typer.Exit(1)
        print(path.read_text(encoding="utf-8"))
