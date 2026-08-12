"""wiretap import — pull live platform config into a local suite + AgentGraph IR."""

from __future__ import annotations

import asyncio

import typer
from rich import print

from wiretap.config import dump_suite
from wiretap.importers import (
    import_bland_pathway,
    import_retell_agent,
    import_vapi_assistant,
)
from wiretap.paths import ensure_layout, graphs_dir, suite_path


def _save_import(suite_name: str, suite, graph) -> None:
    ensure_layout()
    path = suite_path(suite_name)
    dump_suite(suite, path)
    ir_path = graphs_dir() / f"{suite_name}.graph.json"
    ir_path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    print(f"[green]Wrote suite[/green] {path}")
    print(f"[green]Wrote AgentGraph IR[/green] {ir_path}")
    print(f"Scenarios: {', '.join(s.id for s in suite.scenarios)}")


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
    ) -> None:
        """Fetch Retell agent + LLM config → suite + AgentGraph."""
        suite, graph = asyncio.run(import_retell_agent(agent_id))
        _save_import(name, suite, graph)
        print("For live Retell runs: uv sync --extra retell")

    @import_app.command("vapi")
    def import_vapi(
        assistant_id: str = typer.Option(..., "--assistant-id"),
        name: str = typer.Option("vapi", "--name"),
    ) -> None:
        """Fetch Vapi assistant → suite + AgentGraph."""
        suite, graph = asyncio.run(import_vapi_assistant(assistant_id))
        _save_import(name, suite, graph)

    @import_app.command("bland")
    def import_bland(
        pathway_id: str = typer.Option(..., "--pathway-id"),
        name: str = typer.Option("bland", "--name"),
    ) -> None:
        """Fetch Bland pathway → suite + AgentGraph."""
        suite, graph = asyncio.run(import_bland_pathway(pathway_id))
        _save_import(name, suite, graph)
        print(
            "[yellow]Note:[/yellow] Bland live phone dial is deferred; "
            "import still drafts suite + AgentGraph IR."
        )
