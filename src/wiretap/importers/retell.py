"""Retell agent → AgentGraph + SuiteConfig."""

from __future__ import annotations

from typing import Any

import httpx

from wiretap.importers.suite_builder import suite_from_prompt
from wiretap.ir.agent_graph import AgentGraph, GraphEdge, GraphNode, NodeType
from wiretap.models import SuiteConfig
from wiretap.providers.env import require_env

RETELL_API = "https://api.retellai.com"


async def import_retell_agent(agent_id: str) -> tuple[SuiteConfig, AgentGraph]:
    key = require_env("RETELL_API_KEY")
    async with httpx.AsyncClient(
        base_url=RETELL_API,
        headers={"Authorization": f"Bearer {key}"},
        timeout=60.0,
    ) as client:
        agent_resp = await client.get(f"/get-agent/{agent_id}")
        agent_resp.raise_for_status()
        agent = agent_resp.json()

        prompt = ""
        first_message = agent.get("begin_message") or ""
        engine = agent.get("response_engine") or {}
        llm_id = None
        if isinstance(engine, dict):
            llm_id = engine.get("llm_id") or engine.get("id")
            if engine.get("type") == "retell-llm" or llm_id:
                llm_id = llm_id or engine.get("llm_id")

        llm: dict[str, Any] = {}
        if llm_id:
            llm_resp = await client.get(f"/get-retell-llm/{llm_id}")
            if llm_resp.status_code == 200:
                llm = llm_resp.json()
                prompt = llm.get("general_prompt") or ""
                first_message = first_message or llm.get("begin_message") or ""

    graph = _retell_to_graph(agent_id, agent, llm)
    name = agent.get("agent_name") or agent.get("name") or agent_id
    suite = suite_from_prompt(
        platform="retell",
        agent_id=agent_id,
        agent_name=str(name),
        system_prompt=prompt,
        first_message=str(first_message or ""),
        graph=graph,
    )
    return suite, graph


def _retell_to_graph(agent_id: str, agent: dict, llm: dict) -> AgentGraph:
    states = llm.get("states") or []
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    start = llm.get("starting_state") or ""

    if states:
        for st in states:
            sid = str(st.get("name") or st.get("id") or "")
            if not sid:
                continue
            nodes.append(
                GraphNode(
                    id=sid,
                    type=NodeType.CONVERSATION,
                    name=sid,
                    prompt=str(st.get("state_prompt") or ""),
                )
            )
            for edge in st.get("edges") or []:
                dest = edge.get("destination_state_name") or edge.get("destination")
                if dest:
                    edges.append(
                        GraphEdge(
                            id=f"{sid}->{dest}",
                            source=sid,
                            target=str(dest),
                            label=str(edge.get("description") or edge.get("speak_during_transition") or ""),
                        )
                    )
        entry = start or (nodes[0].id if nodes else "start")
    else:
        nodes = [
            GraphNode(
                id="main",
                type=NodeType.CONVERSATION,
                name="main",
                prompt=str(llm.get("general_prompt") or ""),
            ),
            GraphNode(id="end", type=NodeType.END, name="end"),
        ]
        edges = [GraphEdge(id="main->end", source="main", target="end")]
        entry = "main"

    return AgentGraph(
        id=agent_id,
        name=str(agent.get("agent_name") or agent_id),
        entry_node_id=entry,
        nodes=nodes,
        edges=edges,
        source_platform="retell",
        variables=llm.get("default_dynamic_variables") or {},
    )
