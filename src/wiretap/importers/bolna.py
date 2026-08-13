"""Bolna voice agent importer (live dial is phone/PSTN — deferred)."""

from __future__ import annotations

from typing import Any

import httpx

from wiretap.importers.agent_graph import AgentGraph, GraphEdge, GraphNode, NodeType
from wiretap.importers.suite_builder import suite_from_prompt
from wiretap.models import SuiteConfig, TransportKind
from wiretap.providers.env import require_env

BOLNA_API = "https://api.bolna.ai"


async def import_bolna_agent(agent_id: str) -> tuple[SuiteConfig, AgentGraph]:
    key = require_env("BOLNA_API_KEY")
    async with httpx.AsyncClient(
        base_url=BOLNA_API,
        headers={"Authorization": f"Bearer {key}"},
        timeout=60.0,
    ) as client:
        resp = await client.get(f"/v2/agent/{agent_id}")
        if resp.status_code == 404:
            resp = await client.get(f"/agent/{agent_id}")
        resp.raise_for_status()
        data = resp.json()

    cfg = data.get("agent_config") if isinstance(data.get("agent_config"), dict) else data
    name = str(cfg.get("agent_name") or data.get("agent_name") or agent_id)
    prompt = _bolna_prompt(data, cfg)
    first = str(cfg.get("agent_welcome_message") or "")
    graph = AgentGraph(
        id=agent_id,
        name=name,
        entry_node_id="main",
        nodes=[
            GraphNode(id="main", type=NodeType.CONVERSATION, name=name, prompt=prompt),
            GraphNode(id="end", type=NodeType.END, name="end"),
        ],
        edges=[GraphEdge(id="main->end", source="main", target="end")],
        source_platform="bolna",
    )
    suite = suite_from_prompt(
        platform="bolna",
        agent_id=agent_id,
        agent_name=name,
        system_prompt=prompt,
        first_message=first,
        graph=graph,
    )
    suite.agent.token_env = "BOLNA_API_KEY"
    suite.agent.transport = TransportKind.PSTN
    return suite, graph


def _bolna_prompt(data: dict[str, Any], cfg: dict[str, Any]) -> str:
    prompts = data.get("agent_prompts") or {}
    if isinstance(prompts, dict):
        for key in ("task_1", "task1", "default"):
            block = prompts.get(key)
            if isinstance(block, dict) and block.get("system_prompt"):
                return str(block["system_prompt"])
        for block in prompts.values():
            if isinstance(block, dict) and block.get("system_prompt"):
                return str(block["system_prompt"])
    for key in ("system_prompt", "prompt", "instructions"):
        if cfg.get(key):
            return str(cfg[key])
    return str(cfg.get("agent_name") or "Bolna agent")
