"""Minimal LiveKit Agents suite helper (no remote HTTP import — room-based)."""

from __future__ import annotations

from wiretap.importers.agent_graph import AgentGraph, GraphEdge, GraphNode, NodeType
from wiretap.importers.suite_builder import suite_from_prompt
from wiretap.models import SuiteConfig, TransportKind


def suite_for_livekit_agent(
    *,
    room_name: str,
    room_url: str,
    agent_name: str | None = None,
) -> tuple[SuiteConfig, AgentGraph]:
    """Build a local suite targeting a LiveKit room + agent worker.

    Requires LIVEKIT_API_KEY + LIVEKIT_API_SECRET (or LIVEKIT_TOKEN) at simulate time.
    ``room_url`` is the LiveKit WebSocket URL (wss://…livekit.cloud).
    """
    name = (agent_name or room_name or "livekit-agent").strip()
    prompt = (
        f"LiveKit Agents room {room_name!r}. "
        "The live agent worker joins this room; wiretap dials as a participant."
    )
    graph = AgentGraph(
        id=room_name,
        name=name,
        entry_node_id="main",
        nodes=[
            GraphNode(id="main", type=NodeType.CONVERSATION, name=name, prompt=prompt),
            GraphNode(id="end", type=NodeType.END, name="end"),
        ],
        edges=[GraphEdge(id="main->end", source="main", target="end")],
        source_platform="livekit",
    )
    suite = suite_from_prompt(
        platform="livekit",
        agent_id=room_name,
        agent_name=name,
        system_prompt=prompt,
        first_message="Hi, I'd like to talk to the agent.",
        graph=graph,
    )
    suite.agent.transport = TransportKind.WEBRTC
    suite.agent.room_url = room_url
    suite.agent.token_env = "LIVEKIT_API_KEY"
    return suite, graph
