"""Bland pathway → AgentGraph + SuiteConfig."""

from __future__ import annotations

from typing import Any

import httpx

from wiretap.importers.agent_graph import (
    AgentGraph,
    GraphEdge,
    GraphNode,
    GraphTool,
    NodeType,
    graph_tools,
)
from wiretap.importers.suite_builder import suite_from_prompt
from wiretap.models import SuiteConfig, TransportKind
from wiretap.providers.env import require_env

BLAND_API = "https://api.bland.ai"


async def import_bland_pathway(pathway_id: str) -> tuple[SuiteConfig, AgentGraph]:
    key = require_env("BLAND_API_KEY")
    async with httpx.AsyncClient(
        base_url=BLAND_API,
        headers={"authorization": key},  # Bland: raw authorization, no Bearer
        timeout=60.0,
    ) as client:
        resp = await client.get(f"/v1/pathway/{pathway_id}")
        resp.raise_for_status()
        data = resp.json()

    graph = _bland_to_graph(pathway_id, data)
    name = str(data.get("name") or pathway_id)
    # Build prompt from node texts
    prompts = []
    for node in graph.nodes:
        if node.prompt:
            prompts.append(f"[{node.name}] {node.prompt}")
    suite = suite_from_prompt(
        platform="bland",
        agent_id=pathway_id,
        agent_name=name,
        system_prompt="\n".join(prompts) or str(data.get("description") or ""),
        first_message="Hi, I'd like to go through this flow.",
        graph=graph,
    )
    # Bland is typically phone; keep webrtc label for suite but note SIP/PSTN later
    suite.agent.transport = TransportKind.WEBRTC
    suite.agent.token_env = "BLAND_API_KEY"
    return suite, graph


def _bland_to_graph(pathway_id: str, data: dict[str, Any]) -> AgentGraph:
    raw_nodes = data.get("nodes") or []
    raw_edges = data.get("edges") or []
    nodes: list[GraphNode] = []
    tools: list[GraphTool] = []
    seen_tools: set[str] = set()
    entry = ""
    for n in raw_nodes:
        nid = str(n.get("id") or "")
        ndata = n.get("data") or {}
        ntype = str(n.get("type") or "conversation").lower()
        mapped = NodeType.CONVERSATION
        if "end" in ntype:
            mapped = NodeType.END
        elif "transfer" in ntype:
            mapped = NodeType.TRANSFER
        elif "logic" in ntype or "condition" in ntype:
            mapped = NodeType.LOGIC
        if ndata.get("isStart"):
            entry = nid
        node_name = str(ndata.get("name") or nid)
        nodes.append(
            GraphNode(
                id=nid,
                type=mapped,
                name=node_name,
                prompt=str(ndata.get("text") or ndata.get("prompt") or ""),
            )
        )
        # Bland has no tool list — capability lives in the node type itself, and
        # a webhook node's data carries its url, headers and auth.
        for tool in _bland_node_tools(nid, node_name, ntype, ndata):
            if tool.name in seen_tools:
                continue
            seen_tools.add(tool.name)
            tools.append(tool)
    edges = [
        GraphEdge(
            id=str(e.get("id") or f"{e.get('source')}->{e.get('target')}"),
            source=str(e.get("source") or ""),
            target=str(e.get("target") or ""),
            label=str(e.get("label") or ""),
            condition=str(e.get("label") or "") or None,
        )
        for e in raw_edges
        if e.get("source") and e.get("target")
    ]
    if not entry and nodes:
        entry = nodes[0].id
    return AgentGraph(
        id=pathway_id,
        name=str(data.get("name") or pathway_id),
        entry_node_id=entry or "start",
        nodes=nodes,
        edges=edges,
        tools=tools,
        source_platform="bland",
    )


_TOOL_NODE_TYPES = ("webhook", "transfer", "knowledge", "sms", "email", "api")


def _bland_extract_vars(ndata: dict[str, Any]) -> list[str]:
    """``extractVars`` is a list of [name, type, description] triples."""
    raw = ndata.get("extractVars")
    if not isinstance(raw, (list, tuple)):
        return []
    names = []
    for item in raw:
        if isinstance(item, (list, tuple)) and item:
            name = str(item[0]).strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = ""
        if name:
            names.append(name)
    return names


def _bland_node_tools(
    nid: str, name: str, ntype: str, ndata: dict[str, Any]
) -> list[GraphTool]:
    explicit = graph_tools(ndata.get("tools"), node_id=nid)
    if not any(kind in ntype for kind in _TOOL_NODE_TYPES):
        return explicit
    return [
        GraphTool(
            name=name or nid,
            type=ntype,
            description=str(ndata.get("text") or ndata.get("prompt") or "").strip(),
            parameters=_bland_extract_vars(ndata),
            node_id=nid,
        ),
        *explicit,
    ]
