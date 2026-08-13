"""Vapi assistant → AgentGraph + SuiteConfig."""

from __future__ import annotations

from typing import Any

import httpx

from wiretap.importers.agent_graph import (
    AgentGraph,
    GraphEdge,
    GraphNode,
    NodeType,
    as_str_list,
    graph_config,
    graph_tools,
)
from wiretap.importers.suite_builder import suite_from_prompt
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
    # Tools double as transfer/end hints, so they also get a flow node. Only the
    # normalized tool is kept: a Vapi tool's `server` block holds a shared secret
    # and custom auth headers, and node metadata is serialized to disk.
    model = data.get("model") or {}
    tools = graph_tools(model.get("tools"))
    for tool in tools:
        tid = f"tool_{tool.name}"
        nodes.append(
            GraphNode(
                id=tid,
                type=NodeType.TRANSFER if "transfer" in tool.name.lower() else NodeType.LOGIC,
                name=tool.name,
                metadata={"tool_type": tool.type} if tool.type else {},
            )
        )
        edges.append(
            GraphEdge(id=f"main->{tid}", source="main", target=tid, label=tool.name)
        )
    transcriber = data.get("transcriber") or {}
    voice = data.get("voice") or {}
    return AgentGraph(
        id=assistant_id,
        name=name,
        entry_node_id="main",
        nodes=nodes,
        edges=edges,
        tools=tools,
        source_platform="vapi",
        config=graph_config(
            language=(transcriber.get("language") if isinstance(transcriber, dict) else None),
            voice_id=(voice.get("voiceId") if isinstance(voice, dict) else None),
            end_call_phrases=as_str_list(data.get("endCallPhrases")),
            first_message=data.get("firstMessage") or data.get("first_message"),
        ),
    )
