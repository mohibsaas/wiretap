"""wiretap import — pull live platform config into a local suite + AgentGraph IR."""

from __future__ import annotations

import asyncio

import typer
from rich import print

from wiretap.services.generator import DEFAULT_CATEGORIES

_CAT_HELP = (
    "Comma-separated categories "
    f"(default: {','.join(DEFAULT_CATEGORIES)}). "
    "emotional,linguistic,adversarial,operational,factual,compliance,task,other"
)


def _save_import(suite_name: str, suite, graph) -> None:
    from wiretap.paths import ensure_layout, graphs_dir, suite_path
    from wiretap.suite import dump_suite

    ensure_layout()
    path = suite_path(suite_name)
    dump_suite(suite, path)
    ir_path = graphs_dir() / f"{suite_name}.graph.json"
    ir_path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    print(f"[green]Wrote suite[/green] {path}")
    print(f"[green]Wrote AgentGraph IR[/green] {ir_path}")
    by_cat: dict[str, int] = {}
    for s in suite.scenarios:
        key = s.category or "untagged"
        by_cat[key] = by_cat.get(key, 0) + 1
    print(f"Scenarios: {len(suite.scenarios)} ({by_cat})")


def _maybe_generate(
    suite,
    *,
    categories: str,
    tests_per_category: int,
    smoke_only: bool,
) -> None:
    if smoke_only:
        return
    from wiretap.services.generator import fill_suite_scenarios, parse_categories

    cats = parse_categories(categories)
    fill_suite_scenarios(
        suite,
        categories=cats,
        tests_per_category=tests_per_category,
        agent_name=str(suite.agent.agent_id or suite.agent.platform or "agent"),
        model=suite.models.simulator,
    )


def register(app: typer.Typer) -> None:
    import_app = typer.Typer(
        no_args_is_help=True,
        help="Import an agent config into a local suite.",
    )
    app.add_typer(import_app, name="import")

    @import_app.command("retell")
    def import_retell(
        agent_id: str = typer.Option(..., "--agent-id"),
        name: str = typer.Option("retell", "--name", help="Local suite name."),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(
            False, "--smoke-only", help="Skip category tests; keep heuristic smoke suite."
        ),
    ) -> None:
        """Fetch Retell agent → suite + category tests."""
        from wiretap.importers import import_retell_agent

        suite, graph = asyncio.run(import_retell_agent(agent_id))
        _maybe_generate(
            suite,
            categories=categories,
            tests_per_category=tests_per_category,
            smoke_only=smoke_only,
        )
        _save_import(name, suite, graph)
        print(
            "For live Retell runs: set RETELL_API_KEY, then "
            "wiretap simulate --suite retell --all"
        )

    @import_app.command("vapi")
    def import_vapi(
        assistant_id: str = typer.Option(..., "--assistant-id"),
        name: str = typer.Option("vapi", "--name"),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(
            False, "--smoke-only", help="Skip category tests; keep heuristic smoke suite."
        ),
    ) -> None:
        """Fetch Vapi assistant → suite + category tests."""
        from wiretap.importers import import_vapi_assistant

        suite, graph = asyncio.run(import_vapi_assistant(assistant_id))
        _maybe_generate(
            suite,
            categories=categories,
            tests_per_category=tests_per_category,
            smoke_only=smoke_only,
        )
        _save_import(name, suite, graph)

    @import_app.command("bland")
    def import_bland(
        pathway_id: str = typer.Option(..., "--pathway-id"),
        name: str = typer.Option("bland", "--name"),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(
            False, "--smoke-only", help="Skip category tests; keep heuristic smoke suite."
        ),
    ) -> None:
        """Fetch Bland pathway → suite + category tests."""
        from wiretap.importers import import_bland_pathway

        suite, graph = asyncio.run(import_bland_pathway(pathway_id))
        _maybe_generate(
            suite,
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
        agent_id: str = typer.Option(..., "--agent-id"),
        name: str = typer.Option("elevenlabs", "--name"),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(
            False, "--smoke-only", help="Skip category tests; keep heuristic smoke suite."
        ),
    ) -> None:
        """Fetch ElevenLabs Conversational AI agent → suite + category tests."""
        from wiretap.importers import import_elevenlabs_agent

        suite, graph = asyncio.run(import_elevenlabs_agent(agent_id))
        _maybe_generate(
            suite,
            categories=categories,
            tests_per_category=tests_per_category,
            smoke_only=smoke_only,
        )
        _save_import(name, suite, graph)
        print(
            "For live runs: set ELEVENLABS_API_KEY, then "
            "wiretap simulate --suite elevenlabs --all"
        )

    @import_app.command("livekit")
    def import_livekit(
        room: str = typer.Option(..., "--room", help="LiveKit room name (agent_id)."),
        room_url: str = typer.Option(
            ..., "--room-url", help="LiveKit WebSocket URL (wss://…)."
        ),
        agent_name: str = typer.Option("", "--agent-name", help="Display name."),
        name: str = typer.Option("livekit", "--name"),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(
            False, "--smoke-only", help="Skip category tests; keep heuristic smoke suite."
        ),
    ) -> None:
        """Build a suite targeting a LiveKit Agents room (no remote HTTP import)."""
        from wiretap.importers import suite_for_livekit_agent

        suite, graph = suite_for_livekit_agent(
            room_name=room,
            room_url=room_url,
            agent_name=agent_name or None,
        )
        _maybe_generate(
            suite,
            categories=categories,
            tests_per_category=tests_per_category,
            smoke_only=smoke_only,
        )
        _save_import(name, suite, graph)
        print(
            "For live runs: set LIVEKIT_API_KEY + LIVEKIT_API_SECRET "
            "(or LIVEKIT_TOKEN), then wiretap simulate --suite livekit --all"
        )

    @import_app.command("synthflow")
    def import_synthflow(
        model_id: str = typer.Option(..., "--model-id", help="Synthflow model / assistant id."),
        name: str = typer.Option("synthflow", "--name"),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(
            False, "--smoke-only", help="Skip category tests; keep heuristic smoke suite."
        ),
    ) -> None:
        """Fetch Synthflow assistant → suite + category tests."""
        from wiretap.importers import import_synthflow_agent

        suite, graph = asyncio.run(import_synthflow_agent(model_id))
        _maybe_generate(
            suite,
            categories=categories,
            tests_per_category=tests_per_category,
            smoke_only=smoke_only,
        )
        _save_import(name, suite, graph)
        print(
            "For live runs: set SYNTHFLOW_API_KEY plus SYNTHFLOW_FROM_NUMBER / "
            "SYNTHFLOW_TO_NUMBER (E.164)."
        )

    @import_app.command("bolna")
    def import_bolna(
        agent_id: str = typer.Option(..., "--agent-id"),
        name: str = typer.Option("bolna", "--name"),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(3, "--tests-per-category", "-n", min=1, max=10),
        smoke_only: bool = typer.Option(
            False, "--smoke-only", help="Skip category tests; keep heuristic smoke suite."
        ),
    ) -> None:
        """Fetch Bolna agent → suite + category tests."""
        from wiretap.importers import import_bolna_agent

        suite, graph = asyncio.run(import_bolna_agent(agent_id))
        _maybe_generate(
            suite,
            categories=categories,
            tests_per_category=tests_per_category,
            smoke_only=smoke_only,
        )
        _save_import(name, suite, graph)
        print(
            "[yellow]Note:[/yellow] Bolna live phone dial is deferred; "
            "import still drafts suite + AgentGraph IR."
        )
