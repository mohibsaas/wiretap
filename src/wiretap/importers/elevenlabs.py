"""ElevenLabs Conversational AI (Agents) importer."""

from __future__ import annotations

from typing import Any

import httpx

from wiretap.importers.agent_graph import AgentGraph, GraphEdge, GraphNode, NodeType
from wiretap.importers.suite_builder import suite_from_prompt
from wiretap.models import SuiteConfig
from wiretap.providers.env import require_env

ELEVEN_API = "https://api.elevenlabs.io"


async def import_elevenlabs_agent(agent_id: str) -> tuple[SuiteConfig, AgentGraph]:
    key = require_env("ELEVENLABS_API_KEY")
    async with httpx.AsyncClient(
        base_url=ELEVEN_API,
        headers={"xi-api-key": key},
        timeout=60.0,
    ) as client:
        resp = await client.get(f"/v1/convai/agents/{agent_id}")
        resp.raise_for_status()
        data = resp.json()

    name = str(data.get("name") or agent_id)
    prompt, first = _eleven_prompt_and_first(data)
    graph = AgentGraph(
        id=agent_id,
        name=name,
        entry_node_id="main",
        nodes=[
            GraphNode(id="main", type=NodeType.CONVERSATION, name=name, prompt=prompt),
            GraphNode(id="end", type=NodeType.END, name="end"),
        ],
        edges=[GraphEdge(id="main->end", source="main", target="end")],
        source_platform="elevenlabs",
    )
    suite = suite_from_prompt(
        platform="elevenlabs",
        agent_id=agent_id,
        agent_name=name,
        system_prompt=prompt,
        first_message=first,
        graph=graph,
    )
    suite.agent.token_env = "ELEVENLABS_API_KEY"
    return suite, graph


def _eleven_prompt_and_first(data: dict[str, Any]) -> tuple[str, str]:
    cfg = data.get("conversation_config") or {}
    agent = cfg.get("agent") or {}
    prompt_obj = agent.get("prompt") or {}
    if isinstance(prompt_obj, dict):
        prompt = str(prompt_obj.get("prompt") or "")
    else:
        prompt = str(prompt_obj or "")
    first = str(agent.get("first_message") or data.get("first_message") or "")
    if not prompt:
        prompt = str(data.get("name") or "ElevenLabs agent")
    return prompt, first
