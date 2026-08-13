"""Synthflow agent importer."""

from __future__ import annotations

from typing import Any

import httpx

from wiretap.importers.agent_graph import (
    AgentGraph,
    GraphEdge,
    GraphNode,
    GraphTool,
    NodeType,
    graph_config,
    graph_tools,
)
from wiretap.importers.suite_builder import suite_from_prompt
from wiretap.models import SuiteConfig
from wiretap.providers.env import require_env

SYNTHFLOW_API = "https://api.synthflow.ai"


async def import_synthflow_agent(model_id: str) -> tuple[SuiteConfig, AgentGraph]:
    key = require_env("SYNTHFLOW_API_KEY")
    async with httpx.AsyncClient(
        base_url=SYNTHFLOW_API,
        headers={"Authorization": f"Bearer {key}"},
        timeout=60.0,
    ) as client:
        # Platform uses assistants / model id interchangeably across versions
        resp = await client.get(f"/v2/assistants/{model_id}")
        if resp.status_code == 404:
            resp = await client.get(f"/v2/models/{model_id}")
        resp.raise_for_status()
        data = resp.json()

    if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
        data = data["data"]

    name = str(
        data.get("name")
        or data.get("assistant_name")
        or data.get("model_name")
        or model_id
    )
    prompt = _synthflow_prompt(data)
    first = str(
        data.get("greeting")
        or data.get("welcome_message")
        or data.get("first_message")
        or ""
    )
    graph = AgentGraph(
        id=model_id,
        name=name,
        entry_node_id="main",
        nodes=[
            GraphNode(id="main", type=NodeType.CONVERSATION, name=name, prompt=prompt),
            GraphNode(id="end", type=NodeType.END, name="end"),
        ],
        edges=[GraphEdge(id="main->end", source="main", target="end")],
        tools=_synthflow_tools(data),
        source_platform="synthflow",
        variables={"raw_keys": list(data.keys())[:40]},
        config=graph_config(
            language=_synthflow_str(data, "language"),
            voice_id=_synthflow_str(data, "voice_id") or _synthflow_str(data, "voice"),
            first_message=first,
        ),
    )
    suite = suite_from_prompt(
        platform="synthflow",
        agent_id=model_id,
        agent_name=name,
        system_prompt=prompt,
        first_message=first,
        graph=graph,
    )
    suite.agent.token_env = "SYNTHFLOW_API_KEY"
    return suite, graph


def _synthflow_tools(data: dict[str, Any]) -> list[GraphTool]:
    """Synthflow calls these actions, and renames the key across API versions."""
    out: list[GraphTool] = []
    seen: set[str] = set()
    for key in ("actions", "custom_actions", "tools", "functions"):
        for tool in graph_tools(data.get(key)):
            if tool.name in seen:
                continue
            seen.add(tool.name)
            out.append(tool)
    return out


def _synthflow_str(data: dict[str, Any], key: str) -> str:
    """Synthflow returns some of these as nested objects across API versions."""
    val = data.get(key)
    return val.strip() if isinstance(val, str) else ""


def _synthflow_prompt(data: dict[str, Any]) -> str:
    for key in ("prompt", "system_prompt", "instructions", "description"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return str(data.get("name") or "Synthflow agent")
