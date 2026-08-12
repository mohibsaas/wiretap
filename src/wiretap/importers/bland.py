"""Bland pathway → AgentGraph + SuiteConfig."""

from __future__ import annotations

from typing import Any

import httpx

from wiretap.importers.suite_builder import suite_from_prompt
from wiretap.importers.agent_graph import AgentGraph, GraphEdge, GraphNode, NodeType
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
        nodes.append(
            GraphNode(
                id=nid,
                type=mapped,
                name=str(ndata.get("name") or nid),
                prompt=str(ndata.get("text") or ndata.get("prompt") or ""),
            )
        )
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
        source_platform="bland",
    )
