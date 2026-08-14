"""wiretap import — pull live platform config into a local suite + AgentGraph IR."""

from __future__ import annotations

import asyncio
import re

import typer
from rich import print

from wiretap.services.generator import DEFAULT_CATEGORIES

_CAT_HELP = (
    "Comma-separated categories "
    f"(default: {','.join(DEFAULT_CATEGORIES)}). "
    "emotional,linguistic,adversarial,operational,factual,compliance,task,other"
)

_SMOKE_HELP = (
    "Skip category tests; keep heuristic smoke suite. "
    "Category generation sends a sanitized brief of the imported agent "
    "(prompt, tools, flow) to your simulator model."
)
_API_KEY_HELP = "Platform API key (saved to .env). Prompted if missing."
_AGENT_ID_HELP = "Remote agent id (omit to pick interactively from the live list)."


def _prepare_import(platform: str, *, api_key: str | None, smoke_only: bool) -> None:
    """Ensure platform key (+ test-agent LLM when generating scenarios)."""
    from wiretap.cli.prompts import ensure_caller_configured, ensure_platform_key

    ensure_platform_key(platform, api_key=api_key)
    if not smoke_only:
        ensure_caller_configured()


def _safe_suite_stem(raw: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", (raw or "").strip()).strip("_").lower()
    return safe[:48]


def _suite_name_for(
    name: str,
    *,
    platform: str,
    agent_id: str,
    agent_name: str | None,
) -> str:
    """Keep explicit --name; otherwise derive from the selected agent."""
    if name.strip() and name.strip() != platform:
        return name.strip()
    label = (agent_name or "").strip() or agent_id
    stem = _safe_suite_stem(label) or _safe_suite_stem(agent_id) or platform
    if stem.startswith(f"{platform}_"):
        return stem
    return f"{platform}_{stem}"


def _resolve_remote_agent_id(
    platform: str,
    *,
    agent_id: str | None,
    api_key: str | None = None,
    id_label: str = "Agent",
) -> tuple[str, str | None]:
    """Return ``(agent_id, display_name)``. Interactive pick when id omitted."""
    from wiretap.cli import style as ui
    from wiretap.cli.pick import pick_option
    from wiretap.cli.prompts import is_interactive
    from wiretap.importers.remote_agents import list_remote_agents

    explicit = (agent_id or "").strip()
    if explicit:
        return explicit, None

    if not is_interactive():
        ui.err(
            f"Missing {id_label.lower()} id. Pass --agent-id / --assistant-id "
            "or run in an interactive terminal to pick from the live list."
        )
        raise typer.Exit(1)

    with ui.spinner(f"Loading {platform} agents…"):
        remote = list_remote_agents(platform, api_key=api_key)
    agents = list(remote.get("agents") or [])
    if remote.get("source") == "live" and agents:
        ui.rail_text(f"[{ui.ACCENT}]•[/{ui.ACCENT}] Found {len(agents)} agents")
        ui.rail_text()
        picked = pick_option(
            id_label,
            [(a["label"], a["id"]) for a in agents],
            default=str(agents[0]["id"]),
            allow_custom=True,
            custom_prompt=f"Paste custom {id_label.lower()} id",
        )
        name = next((a.get("name") for a in agents if a["id"] == picked), None)
        return picked, str(name) if name else None

    reason = remote.get("error") or "unavailable"
    from wiretap.providers.errors import catalog_error_message, is_auth_error

    if is_auth_error(str(reason)):
        ui.warn(
            catalog_error_message(
                str(reason),
                env_name=f"{platform.upper()}_API_KEY",
                what="agents",
            )
        )
    else:
        ui.warn(f"Could not list {platform} agents ({reason}) — paste an id")
    raw = typer.prompt(f"{id_label} id").strip()
    if not raw:
        ui.err(f"{id_label} id required")
        raise typer.Exit(1)
    return raw, None


def _save_import(suite_name: str, suite, graph) -> None:
    from wiretap.cli import style as ui
    from wiretap.paths import ensure_layout, graphs_dir, suite_path
    from wiretap.suite import dump_suite

    ensure_layout()
    path = suite_path(suite_name)
    dump_suite(suite, path)
    ir_path = graphs_dir() / f"{suite_name}.graph.json"
    ir_path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    ui.ok(f"Wrote suite [{ui.ACCENT}]{path}[/{ui.ACCENT}]")
    ui.muted(f"AgentGraph IR → {ir_path}")
    ui.print_suite_view(suite, name=suite_name, path=str(path))


def _maybe_generate(
    suite,
    graph,
    *,
    categories: str,
    tests_per_category: int,
    smoke_only: bool,
) -> None:
    if smoke_only:
        return
    from wiretap.cli import style as ui
    from wiretap.services.agent_brief import build_agent_brief
    from wiretap.services.generator import fill_suite_scenarios, parse_categories

    cats = parse_categories(categories)
    agent_name = str(
        (graph.name if graph else "")
        or suite.agent.agent_id
        or suite.agent.platform
        or "agent"
    )
    brief = build_agent_brief(graph, suite=suite, agent_name=agent_name)
    if brief:
        print("[dim]Grounding tests in the imported agent config[/dim]")
    with ui.scenario_progress(len(cats) * tests_per_category) as prog:
        fill_suite_scenarios(
            suite,
            categories=cats,
            tests_per_category=tests_per_category,
            agent_name=agent_name,
            model=suite.models.simulator,
            brief=brief,
            on_progress=prog,
        )


def _run_import(label: str, factory):
    """Run an async/sync importer under a spinner."""
    from wiretap.cli import style as ui

    with ui.spinner(f"Importing {label}…"):
        result = factory()
        if asyncio.iscoroutine(result):
            return asyncio.run(result)
        return result


def register(app: typer.Typer) -> None:
    import_app = typer.Typer(
        no_args_is_help=True,
        help="Import an agent config into a local suite.",
    )
    app.add_typer(import_app, name="import")

    @import_app.command("retell")
    def import_retell(
        agent_id: str | None = typer.Option(
            None, "--agent-id", help=_AGENT_ID_HELP
        ),
        name: str = typer.Option("retell", "--name", help="Local suite name."),
        api_key: str | None = typer.Option(None, "--api-key", help=_API_KEY_HELP),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(False, "--smoke-only", help=_SMOKE_HELP),
    ) -> None:
        """Fetch Retell agent → suite + category tests.

        Omit ``--agent-id`` to pick from your live Retell agents (↑↓ search).
        """
        from wiretap.importers import import_retell_agent

        _prepare_import("retell", api_key=api_key, smoke_only=smoke_only)
        agent_id, agent_name = _resolve_remote_agent_id(
            "retell", agent_id=agent_id, api_key=api_key
        )
        suite_name = _suite_name_for(
            name, platform="retell", agent_id=agent_id, agent_name=agent_name
        )
        suite, graph = _run_import(f"retell {agent_id}", lambda: import_retell_agent(agent_id))
        _maybe_generate(
            suite,
            graph,
            categories=categories,
            tests_per_category=tests_per_category,
            smoke_only=smoke_only,
        )
        _save_import(suite_name, suite, graph)
        print(f"Next: [bold]wiretap simulate -s {suite_name} --all[/bold]")

    @import_app.command("vapi")
    def import_vapi(
        assistant_id: str | None = typer.Option(
            None, "--assistant-id", help=_AGENT_ID_HELP
        ),
        name: str = typer.Option("vapi", "--name"),
        api_key: str | None = typer.Option(None, "--api-key", help=_API_KEY_HELP),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(False, "--smoke-only", help=_SMOKE_HELP),
    ) -> None:
        """Fetch Vapi assistant → suite + category tests.

        Omit ``--assistant-id`` to pick from your live Vapi assistants.
        """
        from wiretap.importers import import_vapi_assistant

        _prepare_import("vapi", api_key=api_key, smoke_only=smoke_only)
        assistant_id, agent_name = _resolve_remote_agent_id(
            "vapi",
            agent_id=assistant_id,
            api_key=api_key,
            id_label="Assistant",
        )
        suite_name = _suite_name_for(
            name, platform="vapi", agent_id=assistant_id, agent_name=agent_name
        )
        suite, graph = _run_import(
            f"vapi {assistant_id}", lambda: import_vapi_assistant(assistant_id)
        )
        _maybe_generate(
            suite,
            graph,
            categories=categories,
            tests_per_category=tests_per_category,
            smoke_only=smoke_only,
        )
        _save_import(suite_name, suite, graph)
        print(f"Next: [bold]wiretap simulate -s {suite_name} --all[/bold]")

    @import_app.command("bland")
    def import_bland(
        pathway_id: str = typer.Option(..., "--pathway-id"),
        name: str = typer.Option("bland", "--name"),
        api_key: str | None = typer.Option(None, "--api-key", help=_API_KEY_HELP),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(False, "--smoke-only", help=_SMOKE_HELP),
    ) -> None:
        """Fetch Bland pathway → suite + category tests."""
        from wiretap.importers import import_bland_pathway

        _prepare_import("bland", api_key=api_key, smoke_only=smoke_only)
        suite, graph = _run_import(f"bland {pathway_id}", lambda: import_bland_pathway(pathway_id))
        _maybe_generate(
            suite,
            graph,
            categories=categories,
            tests_per_category=tests_per_category,
            smoke_only=smoke_only,
        )
        _save_import(name, suite, graph)
        print(
            "[yellow]Note:[/yellow] Bland live phone dial is deferred; "
            "import still drafts suite + AgentGraph IR."
        )

    @import_app.command("elevenlabs")
    def import_elevenlabs(
        agent_id: str | None = typer.Option(
            None, "--agent-id", help=_AGENT_ID_HELP
        ),
        name: str = typer.Option("elevenlabs", "--name"),
        api_key: str | None = typer.Option(None, "--api-key", help=_API_KEY_HELP),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(False, "--smoke-only", help=_SMOKE_HELP),
    ) -> None:
        """Fetch ElevenLabs Conversational AI agent → suite + category tests.

        Omit ``--agent-id`` to pick from your live ElevenLabs agents.
        """
        from wiretap.importers import import_elevenlabs_agent

        _prepare_import("elevenlabs", api_key=api_key, smoke_only=smoke_only)
        agent_id, agent_name = _resolve_remote_agent_id(
            "elevenlabs", agent_id=agent_id, api_key=api_key
        )
        suite_name = _suite_name_for(
            name, platform="elevenlabs", agent_id=agent_id, agent_name=agent_name
        )
        suite, graph = _run_import(
            f"elevenlabs {agent_id}", lambda: import_elevenlabs_agent(agent_id)
        )
        _maybe_generate(
            suite,
            graph,
            categories=categories,
            tests_per_category=tests_per_category,
            smoke_only=smoke_only,
        )
        _save_import(suite_name, suite, graph)
        print(f"Next: [bold]wiretap simulate -s {suite_name} --all[/bold]")

    @import_app.command("livekit")
    def import_livekit(
        room: str = typer.Option(..., "--room", help="LiveKit room name (agent_id)."),
        room_url: str = typer.Option(
            ..., "--room-url", help="LiveKit WebSocket URL (wss://…)."
        ),
        agent_name: str = typer.Option("", "--agent-name", help="Display name."),
        name: str = typer.Option("livekit", "--name"),
        api_key: str | None = typer.Option(None, "--api-key", help=_API_KEY_HELP),
        api_secret: str | None = typer.Option(
            None, "--api-secret", help="LIVEKIT_API_SECRET (prompted if missing)."
        ),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(False, "--smoke-only", help=_SMOKE_HELP),
    ) -> None:
        """Build a suite targeting a LiveKit Agents room (no remote HTTP import)."""
        from wiretap.cli.prompts import ensure_caller_configured, ensure_platform_key
        from wiretap.importers import suite_for_livekit_agent

        ensure_platform_key("livekit", api_key=api_key, api_secret=api_secret)
        if not smoke_only:
            ensure_caller_configured()
        suite, graph = _run_import(
            f"livekit {room}",
            lambda: suite_for_livekit_agent(
                room_name=room,
                room_url=room_url,
                agent_name=agent_name or None,
            ),
        )
        _maybe_generate(
            suite,
            graph,
            categories=categories,
            tests_per_category=tests_per_category,
            smoke_only=smoke_only,
        )
        _save_import(name, suite, graph)
        print(f"Next: [bold]wiretap simulate -s {name} --all[/bold]")

    @import_app.command("synthflow")
    def import_synthflow(
        model_id: str = typer.Option(..., "--model-id", help="Synthflow model / assistant id."),
        name: str = typer.Option("synthflow", "--name"),
        api_key: str | None = typer.Option(None, "--api-key", help=_API_KEY_HELP),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(False, "--smoke-only", help=_SMOKE_HELP),
    ) -> None:
        """Fetch Synthflow assistant → suite + category tests."""
        from wiretap.importers import import_synthflow_agent

        _prepare_import("synthflow", api_key=api_key, smoke_only=smoke_only)
        suite, graph = _run_import(f"synthflow {model_id}", lambda: import_synthflow_agent(model_id))
        _maybe_generate(
            suite,
            graph,
            categories=categories,
            tests_per_category=tests_per_category,
            smoke_only=smoke_only,
        )
        _save_import(name, suite, graph)
        print(
            "For live runs also set SYNTHFLOW_FROM_NUMBER / SYNTHFLOW_TO_NUMBER (E.164)."
        )

    @import_app.command("bolna")
    def import_bolna(
        agent_id: str = typer.Option(..., "--agent-id"),
        name: str = typer.Option("bolna", "--name"),
        api_key: str | None = typer.Option(None, "--api-key", help=_API_KEY_HELP),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(False, "--smoke-only", help=_SMOKE_HELP),
    ) -> None:
        """Fetch Bolna agent → suite + category tests."""
        from wiretap.importers import import_bolna_agent

        _prepare_import("bolna", api_key=api_key, smoke_only=smoke_only)
        suite, graph = _run_import(f"bolna {agent_id}", lambda: import_bolna_agent(agent_id))
        _maybe_generate(
            suite,
            graph,
            categories=categories,
            tests_per_category=tests_per_category,
            smoke_only=smoke_only,
        )
        _save_import(name, suite, graph)
        print(
            "[yellow]Note:[/yellow] Bolna live phone dial is deferred; "
            "import still drafts suite + AgentGraph IR."
        )
