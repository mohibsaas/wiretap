"""wiretap init | status — CLI onboarding story (mirrors UI)."""

from __future__ import annotations

import asyncio

import typer

from wiretap.cli import style as ui
from wiretap.services.generator import DEFAULT_CATEGORIES

_CAT_HELP = (
    "Comma-separated categories "
    f"(default: {','.join(DEFAULT_CATEGORIES)}). "
    "emotional,linguistic,adversarial,operational,factual,compliance,task,other"
)


def register(app: typer.Typer) -> None:
    @app.command("status")
    def status_cmd() -> None:
        """Show what's configured (no secret values)."""
        from wiretap.cli.prompts import print_status

        print_status()

    @app.command("init")
    def init_cmd(
        caller_only: bool = typer.Option(
            False,
            "--caller-only",
            help="Only configure the test agent (LLM + STT/TTS); skip live agent.",
        ),
        force: bool = typer.Option(
            False,
            "--force",
            "-f",
            help="Re-run test-agent setup even if already configured.",
        ),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(
            5, "--tests-per-category", "-n", min=1, max=10
        ),
    ) -> None:
        """Interactive first-run setup (test agent → optional live agent → suite).

        Writes API keys to .env only. Same services as the UI onboarding flow.
        """
        from wiretap.cli.prompts import (
            configure_caller_interactive,
            ensure_caller_configured,
            ensure_platform_key,
            is_interactive,
            print_status,
        )
        from wiretap.services.generator import parse_categories
        from wiretap.services.onboard import (
            connect_agent,
            generate_onboard_suite,
            load_onboard_state,
            onboard_status,
            save_onboard_state,
        )

        if not is_interactive():
            ui.err("wiretap init needs an interactive terminal.")
            ui.muted("Set keys in .env (see .env.example) or run from a TTY.")
            raise typer.Exit(1)

        ui.banner(
            "wiretap init",
            "Local setup · keys → ~/.wiretap/.env · never printed",
        )

        # Step 1 — test agent
        ui.step(
            1,
            3,
            "Test agent",
            detail="LLM + STT/TTS used by the simulated caller",
        )
        status = onboard_status()
        if status.get("caller_configured") and not force:
            ui.muted("Already configured — use --force to redo.")
            ensure_caller_configured(force=False)
            ui.ok("Test agent ready")
        else:
            configure_caller_interactive()

        if caller_only:
            print_status()
            ui.next_cmd("wiretap import retell --agent-id …")
            ui.next_cmd("wiretap ui run", hint="Or")
            return

        # Step 2 — live agent
        ui.step(
            2,
            3,
            "Live agent",
            detail="Import a production voice agent to dial during simulate",
        )
        connect = typer.confirm("Connect a live agent now?", default=True)
        if not connect:
            state = load_onboard_state()
            state["platform"] = state.get("platform") or "custom"
            save_onboard_state(state)
            ui.warn("Skipped live agent — you can import later.")
            ui.next_cmd("wiretap import retell --agent-id …")
            print_status()
            return

        platforms = [
            "retell",
            "vapi",
            "elevenlabs",
            "livekit",
            "synthflow",
            "bolna",
            "custom",
        ]
        ui.info("Choose a platform")
        ui.platform_table(platforms, default="retell")
        platform = typer.prompt("Platform", default="retell").strip().lower()
        if platform not in platforms:
            ui.warn(f"Unknown platform {platform!r} — using custom")
            platform = "custom"

        agent_id: str | None = None
        room_url: str | None = None
        api_key: str | None = None
        api_secret: str | None = None

        if platform != "custom":
            ensure_platform_key(platform)
            if platform == "livekit":
                agent_id = typer.prompt("LiveKit room name").strip()
                room_url = typer.prompt("LiveKit URL (wss://…)").strip()
            elif platform == "synthflow":
                agent_id = typer.prompt("Synthflow model / assistant id").strip()
            else:
                agent_id = typer.prompt("Agent id").strip()
        else:
            agent_id = (
                typer.prompt("Name (optional)", default="custom").strip() or "custom"
            )

        try:
            with ui.spinner(f"Connecting {platform} agent…"):
                result = asyncio.run(
                    connect_agent(
                        platform=platform,
                        agent_id=agent_id,
                        api_key=api_key,
                        api_secret=api_secret,
                        room_url=room_url,
                    )
                )
        except (ValueError, RuntimeError, OSError) as exc:
            ui.err(f"Connect failed: {exc}")
            raise typer.Exit(1) from exc

        ui.ok(
            f"Connected [bold]{result.get('platform')}[/bold] "
            f"· suite [{ui.ACCENT}]{result.get('suite_name')}[/{ui.ACCENT}]"
        )
        if result.get("live_deferred"):
            ui.warn("Live dial for this platform is deferred (import only).")

        # Step 3 — generate suite
        ui.step(
            3,
            3,
            "Test suite",
            detail="Category scenarios for the connected agent",
        )
        if not typer.confirm("Generate category test suite now?", default=True):
            print_status()
            ui.next_cmd(
                f'wiretap suite generate -s {result.get("suite_name")} -p "…"'
            )
            return

        purpose = typer.prompt(
            "Purpose (what does the agent do?)",
            default="",
        ).strip()
        cats = parse_categories(categories)
        try:
            with ui.scenario_progress(len(cats) * tests_per_category) as prog:
                gen = generate_onboard_suite(
                    purpose=purpose,
                    categories=cats,
                    tests_per_category=tests_per_category,
                    on_progress=prog,
                )
        except ValueError as exc:
            ui.err(f"Generate failed: {exc}")
            raise typer.Exit(1) from exc

        ui.ok(
            f"Generated [{ui.ACCENT}]{gen.get('path')}[/{ui.ACCENT}]  "
            f"[bold]{gen.get('scenario_count')}[/bold] scenarios"
        )
        suite_name = gen.get("suite_name") or result.get("suite_name")
        try:
            from wiretap.paths import suite_path
            from wiretap.suite import load_suite

            sp = suite_path(str(suite_name))
            if sp.is_file():
                ui.print_suite_view(load_suite(sp), name=str(suite_name), path=str(sp))
        except Exception:
            pass
        print_status()
        ui.next_cmd(f"wiretap simulate -s {suite_name} --all", hint="Run")
