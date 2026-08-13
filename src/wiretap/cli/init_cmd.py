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
        """Interactive first-run setup (test agent → live agent → suite → phone).

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
            4,
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
            4,
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
            4,
            "Test suite",
            detail="Category scenarios for the connected agent",
        )
        if not typer.confirm("Generate category test suite now?", default=True):
            _phone_step(result.get("suite_name"))
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

        dialing = _phone_step(suite_name)
        print_status()
        run = f"wiretap simulate -s {suite_name} --all"
        ui.next_cmd(f"{run} --transport phone" if dialing else run, hint="Run")


def _phone_step(suite_name: object) -> bool:
    """Step 4 — optional Twilio setup so ``simulate`` can place a real call.

    Everything before this already saved, so a decline (or a missing extra) is
    a warning rather than a failed init.
    """
    from wiretap.cli.prompts import (
        ensure_agent_number,
        ensure_pstn_configured,
        require_pstn_extra,
    )
    from wiretap.paths import suite_path
    from wiretap.suite import load_suite

    ui.step(
        4,
        4,
        "Phone testing",
        detail="Optional — dial the agent's real number instead of the web",
    )
    if not typer.confirm("Test this agent over a real phone call?", default=False):
        ui.muted("Skipped — wiretap simulate --transport phone sets this up later.")
        return False

    path = suite_path(str(suite_name or ""))
    try:
        require_pstn_extra()
        ensure_pstn_configured()
        number = ensure_agent_number(load_suite(path)) if path.is_file() else ""
    except typer.Exit:
        ui.warn("Phone testing not configured — retry with simulate --transport phone.")
        return False
    except (ValueError, RuntimeError, OSError) as exc:
        ui.warn(f"Phone testing not configured: {exc}")
        return False

    if number:
        ui.ok(f"Phone testing ready — dialing [bold]{number}[/bold]")
    return bool(number)
