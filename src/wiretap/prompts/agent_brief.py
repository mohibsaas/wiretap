"""Sanitize imported agent config into a brief for suite-generation prompts.

Never put raw secrets, tokens, or full ``raw`` platform dumps into LLM context.
"""

from __future__ import annotations

import re
from typing import Any

from wiretap.importers.agent_graph import AgentGraph

# Soft cap so suite-generation prompts stay within reasonable context.
_MAX_BRIEF_CHARS = 4000
_MAX_NODE_PROMPT_CHARS = 400
_SECRETISH = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|authorization|bearer)\b\s*[:=]\s*\S+"
)


def sanitize_text(text: str, *, max_chars: int | None = None) -> str:
    """Strip secret-looking assignments and optionally truncate."""
    cleaned = _SECRETISH.sub(r"\1: [REDACTED]", text or "")
    cleaned = cleaned.strip()
    if max_chars is not None and len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 1].rstrip() + "…"
    return cleaned


def agent_brief_from_graph(
    graph: AgentGraph,
    *,
    purpose: str = "",
    max_chars: int = _MAX_BRIEF_CHARS,
) -> dict[str, Any]:
    """Build a compact, redacted brief from AgentGraph IR."""
    nodes_out: list[dict[str, str]] = []
    for node in graph.nodes[:24]:
        entry: dict[str, str] = {
            "id": node.id,
            "type": node.type.value if hasattr(node.type, "value") else str(node.type),
            "name": (node.name or node.id).strip(),
        }
        prompt = sanitize_text(node.prompt, max_chars=_MAX_NODE_PROMPT_CHARS)
        if prompt:
            entry["instructions"] = prompt
        nodes_out.append(entry)

    edges_out: list[dict[str, str]] = []
    for edge in graph.edges[:40]:
        item: dict[str, str] = {
            "from": edge.source,
            "to": edge.target,
        }
        if edge.label:
            item["label"] = sanitize_text(edge.label, max_chars=120)
        if edge.condition:
            item["when"] = sanitize_text(edge.condition, max_chars=160)
        edges_out.append(item)

    brief: dict[str, Any] = {
        "agent_id": graph.id,
        "agent_display_name": (graph.name or graph.id).strip(),
        "source_platform": graph.source_platform,
        "entry_node_id": graph.entry_node_id,
        "flow_nodes": nodes_out,
        "flow_edges": edges_out,
    }
    purpose_bit = sanitize_text(purpose, max_chars=500)
    if purpose_bit:
        brief["stated_purpose"] = purpose_bit

    # Enforce overall size by trimming node instruction bodies first.
    packed = _trim_brief(brief, max_chars=max_chars)
    return packed


def agent_brief_from_purpose_only(
    *,
    agent_name: str,
    purpose: str,
) -> dict[str, Any]:
    """Minimal brief when no graph IR is available."""
    return {
        "agent_display_name": (agent_name or "agent").strip() or "agent",
        "stated_purpose": sanitize_text(purpose, max_chars=800)
        or "(purpose not provided — invent realistic domain-agnostic phone scenarios)",
        "flow_nodes": [],
        "flow_edges": [],
        "note": (
            "No imported AgentGraph was supplied. "
            "Ground scenarios in stated_purpose only; do not invent proprietary policies."
        ),
    }


def _trim_brief(brief: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    import json

    def size(obj: dict[str, Any]) -> int:
        return len(json.dumps(obj, ensure_ascii=False))

    while size(brief) > max_chars and brief.get("flow_nodes"):
        nodes = brief["flow_nodes"]
        # Drop instructions from the longest node first.
        longest = max(
            range(len(nodes)),
            key=lambda i: len(nodes[i].get("instructions") or ""),
        )
        if nodes[longest].get("instructions"):
            nodes[longest].pop("instructions", None)
        else:
            nodes.pop(longest)
    if size(brief) > max_chars and brief.get("flow_edges"):
        brief["flow_edges"] = brief["flow_edges"][: max(8, len(brief["flow_edges"]) // 2)]
    if size(brief) > max_chars:
        brief["truncated"] = True
        brief.pop("flow_edges", None)
    return brief


__all__ = [
    "agent_brief_from_graph",
    "agent_brief_from_purpose_only",
    "sanitize_text",
]
