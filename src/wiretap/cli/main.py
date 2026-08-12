"""Typer CLI entry — Commander-style command tree."""

from __future__ import annotations

import typer
from rich import print

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Test live voice agents from the CLI.",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        from wiretap import __version__

        print(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=_version_callback,
        is_eager=True,
        help="Show version.",
    ),
) -> None:
    from wiretap.services.secrets import load_dotenv

    load_dotenv()
    _ = version


def _register() -> None:
    # Import command modules only when the CLI process starts registering —
    # keep this function's imports local so tooling can import `app` lightly.
    from wiretap.cli import (
        export_cmd,
        import_cmd,
        report_cmd,
        simulate_cmd,
        suite_cmd,
        ui_cmd,
    )

    suite_cmd.register(app)
    simulate_cmd.register(app)
    report_cmd.register(app)
    export_cmd.register(app)
    import_cmd.register(app)
    ui_cmd.register(app)


_register()


if __name__ == "__main__":
    app()
