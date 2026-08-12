"""wiretap export."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich import print

from wiretap.paths import suite_path


def register(app: typer.Typer) -> None:
    @app.command("export")
    def export_cmd(
        out: Path = typer.Option(
            ..., "--out", "-o", help="Destination file or directory."
        ),
        suite: str = typer.Option("default", "--suite", "-s"),
    ) -> None:
        """Copy a local suite out of .wiretap/ (for git/CI)."""
        src = suite_path(suite)
        if not src.is_file():
            print(f"[red]Not found:[/red] {src}")
            raise typer.Exit(1)
        dest = out
        if dest.exists() and dest.is_dir():
            dest = dest / src.name
        elif dest.suffix not in {".yaml", ".yml"}:
            dest.mkdir(parents=True, exist_ok=True)
            dest = dest / src.name
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"[green]Exported[/green] {src} → {dest}")
