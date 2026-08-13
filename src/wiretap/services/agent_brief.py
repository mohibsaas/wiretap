"""Sanitized agent brief for LLM suite generation.

Import captures the live agent's prompt, tools and flow into an ``AgentGraph``.
This turns that IR into a compact, JSON-serializable brief so generated
scenarios are grounded in the real agent instead of its name alone.

Everything here leaves the machine in an LLM payload, so text is scrubbed of
secrets and contact details and hard-capped before it is handed over.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from wiretap.importers.agent_graph import AgentGraph, GraphTool, NodeType, as_str_list
from wiretap.importers.suite_builder import first_instructive_line
from wiretap.models import SuiteConfig
from wiretap.paths import graphs_dir

REDACTED = "[REDACTED]"
TRUNCATION_MARKER = "…[truncated]"

PROMPT_EXCERPT_CAP = 3000
SUMMARY_CAP = 1200
NODE_EXCERPT_CAP = 240
TOOL_DESC_CAP = 160
MAX_FLOW_NODES = 12
MAX_TOOLS = 16

# Tool names implying a side effect the caller cannot take back — useful for
# generating confirmation / escalation scenarios.
IRREVERSIBLE_HINTS = (
    "transfer",
    "book",
    "cancel",
    "refund",
    "charge",
    "payment",
    "pay",
    "delete",
    "remove",
    "send",
    "schedule",
    "reschedule",
    "submit",
)

_ENV_LINE = re.compile(r"^\s*[A-Z][A-Z0-9_]{2,}\s*=\s*\S.*$", re.MULTILINE)
_CREDENTIALED_URL = re.compile(r"([a-zA-Z][\w+.\-]*://)[^\s/@]+:[^\s/@]+@")
_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+")
_PHONE = re.compile(r"\+?\d[\d\s().\-]{7,}\d")
_DIGIT_RUN = re.compile(r"\b\d{6,}\b")

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:sk|pk|rk)[-_][A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\b"),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),
)

_GOAL_HINTS = ("your job", "your goal", "you should", "you must", "your task", "help the")
_CONSTRAINT_HINTS = ("never", "do not", "don't", "must not", "always", "only if", "refuse")


def _redact_phone(match: re.Match[str]) -> str:
    """Only redact when the run really looks like a phone number."""
    digits = sum(ch.isdigit() for ch in match.group(0))
    return REDACTED if digits >= 9 else match.group(0)


def sanitize_text(text: str, *, cap: int) -> str:
    """Strip secrets and contact details, then hard-cap the length.

    Redaction runs before truncation so a cut cannot leave half a secret behind.
    Best-effort by design: the cap is what actually bounds the exposure.
    """
    if not text:
        return ""
    out = _ENV_LINE.sub("", str(text))
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(REDACTED, out)
    out = _CREDENTIALED_URL.sub(rf"\1{REDACTED}@", out)
    out = _EMAIL.sub(REDACTED, out)
    out = _PHONE.sub(_redact_phone, out)
    out = _DIGIT_RUN.sub(REDACTED, out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    if len(out) > cap:
        out = out[:cap].rstrip() + TRUNCATION_MARKER
    return out


def _system_prompt(graph: AgentGraph | None) -> str:
    """Entry node prompt first, then the remaining state prompts."""
    if graph is None:
        return ""
    ordered = sorted(
        (n for n in graph.nodes if n.prompt.strip()),
        key=lambda n: 0 if n.id == graph.entry_node_id else 1,
    )
    if not ordered:
        return ""
    if len(ordered) == 1:
        return ordered[0].prompt.strip()
    return "\n\n".join(f"[{n.name or n.id}] {n.prompt.strip()}" for n in ordered)


def _summarize(prompt: str, *, agent_name: str) -> str:
    """Heuristic structure: role, goals, constraints. No LLM call by design."""
    if not prompt.strip():
        return ""
    role = first_instructive_line(prompt, limit=240)
    goals: list[str] = []
    constraints: list[str] = []
    for raw in prompt.splitlines():
        line = raw.strip(" -*\t").strip()
        if len(line) < 8:
            continue
        low = line.lower()
        if line[:240] == role:
            continue
        if any(h in low for h in _CONSTRAINT_HINTS) and len(constraints) < 6:
            constraints.append(line[:200])
        elif any(h in low for h in _GOAL_HINTS) and len(goals) < 6:
            goals.append(line[:200])
    parts: list[str] = []
    if role:
        parts.append(f"Role: {role}")
    elif agent_name:
        parts.append(f"Role: {agent_name}")
    if goals:
        parts.append("Goals:\n" + "\n".join(f"- {g}" for g in goals))
    if constraints:
        parts.append("Stated constraints:\n" + "\n".join(f"- {c}" for c in constraints))
    return "\n".join(parts)


def _tool_entry(name: str, tool: Any) -> dict[str, Any]:
    description = ""
    if isinstance(tool, dict):
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else {}
        name = str(fn.get("name") or tool.get("name") or tool.get("type") or name)
        description = str(fn.get("description") or tool.get("description") or "")
    entry: dict[str, Any] = {"name": name.strip()}
    if description.strip():
        entry["description"] = sanitize_text(description, cap=TOOL_DESC_CAP)
    return entry


def _graph_tool_entry(tool: GraphTool) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": tool.name.strip()}
    if tool.type and tool.type != tool.name:
        entry["type"] = tool.type.strip()
    if tool.description.strip():
        entry["description"] = sanitize_text(tool.description, cap=TOOL_DESC_CAP)
    if tool.parameters:
        # Argument names tell the generator what the agent must collect.
        entry["parameters"] = [p.strip() for p in tool.parameters if p.strip()]
    return entry


def _tools(graph: AgentGraph | None) -> list[dict[str, Any]]:
    """First-class graph tools, then flow nodes that imply one.

    The node pass also covers graphs written before ``AgentGraph.tools`` existed,
    since these files persist under ``.wiretap/graphs``.
    """
    if graph is None:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(entry: dict[str, Any]) -> bool:
        if not entry["name"] or entry["name"] in seen:
            return True
        seen.add(entry["name"])
        out.append(entry)
        return len(out) < MAX_TOOLS

    for tool in graph.tools:
        if not add(_graph_tool_entry(tool)):
            return out
    for node in list(graph.nodes) + list(graph.global_nodes):
        tool = node.metadata.get("tool") if node.metadata else None
        if tool is None and node.type is not NodeType.TRANSFER:
            continue
        if not add(_tool_entry(node.name or node.id, tool)):
            return out
    return out


def _flow_nodes(graph: AgentGraph | None) -> list[dict[str, str]]:
    if graph is None or len(graph.nodes) <= 1:
        return []
    out: list[dict[str, str]] = []
    for node in graph.nodes[:MAX_FLOW_NODES]:
        entry = {"id": node.id, "type": node.type.value}
        if node.prompt.strip():
            entry["excerpt"] = sanitize_text(node.prompt, cap=NODE_EXCERPT_CAP)
        out.append(entry)
    return out


def _irreversible(tools: list[dict[str, Any]]) -> list[str]:
    out = []
    for tool in tools:
        low = tool["name"].lower()
        if any(hint in low for hint in IRREVERSIBLE_HINTS):
            out.append(tool["name"])
    return out


def build_agent_brief(
    graph: AgentGraph | None,
    *,
    suite: SuiteConfig | None = None,
    purpose: str = "",
    agent_name: str = "",
) -> dict[str, Any]:
    """Sanitized, JSON-serializable agent brief for the generation prompt.

    Returns ``{}`` when there is nothing useful to say — callers then fall back
    to purpose plus category guidance. Never includes ``token_env`` or secrets.
    """
    config = dict(graph.config) if graph is not None else {}
    prompt = _system_prompt(graph)
    tools = _tools(graph)
    brief: dict[str, Any] = {
        "agent_name": (agent_name or (graph.name if graph else "")).strip(),
        "purpose": purpose.strip(),
        "summary": sanitize_text(_summarize(prompt, agent_name=agent_name), cap=SUMMARY_CAP),
        "tools": tools,
        "irreversible_tools": _irreversible(tools),
        "flow_nodes": _flow_nodes(graph),
        "first_message": sanitize_text(str(config.get("first_message") or ""), cap=NODE_EXCERPT_CAP),
        "prompt_excerpt": sanitize_text(prompt, cap=PROMPT_EXCERPT_CAP),
        "language": str(config.get("language") or ""),
        "end_call_phrases": as_str_list(config.get("end_call_phrases")),
    }
    if suite is not None:
        # token_env is deliberately excluded — it never goes to the model.
        brief["platform"] = suite.agent.platform or ""
        brief["agent_id"] = suite.agent.agent_id or ""
    compact = {k: v for k, v in brief.items() if v}
    # Name/purpose alone is not grounding — that is the purpose-only path.
    if not any(compact.get(k) for k in ("summary", "prompt_excerpt", "tools", "flow_nodes")):
        return {}
    return compact


def load_agent_graph(name: str, *, cwd: Path | None = None) -> AgentGraph | None:
    """Read the graph IR an import wrote. None when absent or unreadable."""
    if not name:
        return None
    path = graphs_dir(cwd) / f"{name}.graph.json"
    if not path.is_file():
        return None
    try:
        return AgentGraph.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return None


def brief_for_suite(
    name: str,
    *,
    suite: SuiteConfig | None = None,
    purpose: str = "",
    agent_name: str = "",
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Brief for a locally stored suite, from its graph IR when one exists."""
    graph = load_agent_graph(name, cwd=cwd)
    return build_agent_brief(
        graph,
        suite=suite,
        purpose=purpose,
        agent_name=agent_name,
    )


def end_call_phrases(brief: dict[str, Any] | None) -> list[str]:
    """Phrases the caller must never say — they hang up the call under test."""
    if not brief:
        return []
    return as_str_list(brief.get("end_call_phrases"))


__all__ = [
    "PROMPT_EXCERPT_CAP",
    "REDACTED",
    "TRUNCATION_MARKER",
    "brief_for_suite",
    "build_agent_brief",
    "end_call_phrases",
    "load_agent_graph",
    "sanitize_text",
]
