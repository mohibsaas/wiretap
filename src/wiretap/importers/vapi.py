"""Vapi assistant → AgentGraph + SuiteConfig."""

from __future__ import annotations

from typing import Any

import httpx

from wiretap.importers.suite_builder import suite_from_prompt
from wiretap.importers.agent_graph import AgentGraph, GraphEdge, GraphNode, NodeType
from wiretap.models import SuiteConfig
from wiretap.providers.env import require_env

VAPI_API = "https://api.vapi.ai"


async def import_vapi_assistant(assistant_id: str) -> tuple[SuiteConfig, AgentGraph]:
    key = require_env("VAPI_API_KEY")
    async with httpx.AsyncClient(
        base_url=VAPI_API,
        headers={"Authorization": f"Bearer {key}"},
        timeout=60.0,
    ) as client:
        resp = await client.get(f"/assistant/{assistant_id}")
        resp.raise_for_status()
        data = resp.json()

    prompt = _vapi_system_prompt(data)
    first = str(data.get("firstMessage") or data.get("first_message") or "")
    name = str(data.get("name") or assistant_id)
    graph = _vapi_to_graph(assistant_id, name, prompt, data)
    suite = suite_from_prompt(
        platform="vapi",
        agent_id=assistant_id,
        agent_name=name,
        system_prompt=prompt,
        first_message=first,
        graph=graph,
    )
    return suite, graph


def _vapi_system_prompt(data: dict[str, Any]) -> str:
    model = data.get("model") or {}
    messages = model.get("messages") or []
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "system":
            content = msg.get("content")
            if isinstance(content, str):
                parts.append(content)
    return "\n\n".join(parts)


def _vapi_to_graph(assistant_id: str, name: str, prompt: str, data: dict) -> AgentGraph:
    nodes = [
        GraphNode(id="main", type=NodeType.CONVERSATION, name=name, prompt=prompt),
        GraphNode(id="end", type=NodeType.END, name="end"),
    ]
    edges = [GraphEdge(id="main->end", source="main", target="end")]
    # Tools as transfer/end hints
    model = data.get("model") or {}
    for i, tool in enumerate(model.get("tools") or []):
        if not isinstance(tool, dict):
            continue
        fn = (tool.get("function") or {}).get("name") or tool.get("type") or f"tool_{i}"
        tid = f"tool_{fn}"
        nodes.append(
            GraphNode(
                id=tid,
                type=NodeType.TRANSFER if "transfer" in str(fn).lower() else NodeType.LOGIC,
                name=str(fn),
                metadata={"tool": tool},
            )
        )
        edges.append(GraphEdge(id=f"main->{tid}", source="main", target=tid, label=str(fn)))
    return AgentGraph(
        id=assistant_id,
        name=name,
        entry_node_id="main",
        nodes=nodes,
        edges=edges,
        source_platform="vapi",
    )
