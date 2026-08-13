"""ElevenLabs Conversational AI (Agents) importer."""

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

ELEVEN_API = "https://api.elevenlabs.io"

# Referenced tools cost one request each; enough to ground tests, not a crawl.
MAX_TOOL_LOOKUPS = 20


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
        tools = await _eleven_tools(client, data)

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
        tools=tools,
        source_platform="elevenlabs",
        config=_eleven_config(data, first),
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


def _eleven_prompt_obj(data: dict[str, Any]) -> dict[str, Any]:
    cfg = data.get("conversation_config") or {}
    agent = cfg.get("agent") if isinstance(cfg, dict) else {}
    prompt = agent.get("prompt") if isinstance(agent, dict) else {}
    return prompt if isinstance(prompt, dict) else {}


async def _eleven_tools(client: httpx.AsyncClient, data: dict[str, Any]) -> list[GraphTool]:
    """Inline tools, then the ones referenced only by id.

    Newer agents carry ``tool_ids`` instead of inline definitions, so skipping
    the lookup would silently import an agent as if it had no tools. A failed
    lookup is not fatal — import degrades to whatever it could resolve.
    """
    prompt = _eleven_prompt_obj(data)
    tools = graph_tools(prompt.get("tools"))
    seen = {t.name for t in tools}
    tool_ids = prompt.get("tool_ids")
    if not isinstance(tool_ids, (list, tuple)):
        return tools
    for tool_id in list(tool_ids)[:MAX_TOOL_LOOKUPS]:
        if not isinstance(tool_id, str) or not tool_id.strip():
            continue
        try:
            resp = await client.get(f"/v1/convai/tools/{tool_id}")
        except httpx.HTTPError:
            continue
        if resp.status_code != 200:
            continue
        body = resp.json()
        payload = body.get("tool_config") if isinstance(body, dict) else None
        for tool in graph_tools(payload if isinstance(payload, dict) else body):
            if tool.name in seen:
                continue
            seen.add(tool.name)
            tools.append(tool)
    return tools


def _eleven_config(data: dict[str, Any], first_message: str) -> dict[str, Any]:
    cfg = data.get("conversation_config") or {}
    agent = cfg.get("agent") or {}
    tts = cfg.get("tts") or {}
    return graph_config(
        language=(agent.get("language") if isinstance(agent, dict) else None),
        voice_id=(tts.get("voice_id") if isinstance(tts, dict) else None),
        first_message=first_message,
    )


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
