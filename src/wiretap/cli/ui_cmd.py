"""wiretap ui — local dashboard server."""

from __future__ import annotations

import webbrowser

import typer
from rich import print

from wiretap.paths import ensure_layout, wiretap_root


def register(app: typer.Typer) -> None:
    ui_app = typer.Typer(
        no_args_is_help=True,
        help="Local ops dashboard (onboarding, suites, evaluations).",
    )
    app.add_typer(ui_app, name="ui")

    @ui_app.command("run")
    def ui_run(
        host: str = typer.Option("127.0.0.1", "--host"),
        port: int = typer.Option(8787, "--port"),
        open_browser: bool = typer.Option(
            True, "--open/--no-open", help="Open the dashboard in a browser."
        ),
    ) -> None:
        """Start the local dashboard (API + SPA) on localhost."""
        import uvicorn

        from wiretap.cli import style as ui
        from wiretap.ui.app import create_app

        ensure_layout()
        url = f"http://{host}:{port}"
        with ui.spinner("Starting dashboard…"):
            fastapi_app = create_app()
        print(f"[{ui.ACCENT}]wiretap ui[/{ui.ACCENT}] {url}")
        print(f"[dim]data[/dim] {wiretap_root()}")
        if open_browser and host in {"127.0.0.1", "localhost"}:
            webbrowser.open(url)

        uvicorn.run(
            fastapi_app,
            host=host,
            port=port,
            log_level="info",
        )
