"""wiretap simulator — view / update the simulated party (LLM + speech)."""

from __future__ import annotations

import typer

from wiretap.cli import style as ui


def register(app: typer.Typer) -> None:
    sim_app = typer.Typer(
        help="Configure the simulator (LLM / STT / TTS) without re-running init.",
        no_args_is_help=False,
    )
    app.add_typer(sim_app, name="simulator")

    @sim_app.callback(invoke_without_command=True)
    def simulator_root(ctx: typer.Context) -> None:
        """Show compact simulator status (use ``wiretap status`` for everything)."""
        if ctx.invoked_subcommand is not None:
            return
        from wiretap.cli.prompts import print_simulator_status

        print_simulator_status()

    @sim_app.command("configure")
    def simulator_configure() -> None:
        """Update selected simulator settings (LLM, models, STT, TTS, voice).

        Asks what to change first when a simulator already exists. Does not touch
        live-agent import or suites.
        """
        from wiretap.cli.prompts import (
            configure_caller_interactive,
            is_interactive,
            pick_simulator_sections,
            print_simulator_status,
        )
        from wiretap.services.onboard import onboard_status

        if not is_interactive():
            ui.err("wiretap simulator configure needs an interactive terminal.")
            ui.muted("Or edit ~/.wiretap/.env and onboard.json manually.")
            raise typer.Exit(1)

        status = onboard_status()
        caller = status.get("caller") or {}
        ui.banner(
            "wiretap simulator",
            "Update LLM · STT · TTS for the simulated party on the call",
        )

        if status.get("caller_configured"):
            ui.muted(
                f"Current  {caller.get('llm_provider') or '—'} · "
                f"{caller.get('stt') or '—'} STT · {caller.get('tts') or '—'} TTS"
            )
            sections = pick_simulator_sections()
        else:
            ui.muted("No simulator yet — walking through full setup.")
            sections = {"all"}

        ui.step(
            1,
            1,
            "Simulator",
            detail="LLM + STT/TTS used when dialing the live agent",
        )
        configure_caller_interactive(sections=sections)
        print_simulator_status()
        ui.next_cmd("wiretap simulate --all")
