"""AgentGraph intermediate representation (data only — not executed)."""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    CONVERSATION = "conversation"
    LOGIC = "logic"
    EXTRACT = "extract"
    END = "end"
    TRANSFER = "transfer"


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str | None = None
    condition: str | None = None


class GraphNode(BaseModel):
    id: str
    type: NodeType
    name: str = ""
    prompt: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphTool(BaseModel):
    """A tool the live agent can invoke during a call.

    Descriptive fields only. Build these with :func:`graph_tools` rather than
    copying a platform payload: tool definitions carry webhook URLs, auth
    headers and API tokens, and this model is written to ``.wiretap/graphs``.
    """

    name: str
    type: str = ""
    description: str = ""
    # Parameter names only — never the schema, which can carry example values.
    parameters: list[str] = Field(default_factory=list)
    # Node the tool is scoped to; empty when callable anywhere in the flow.
    node_id: str = ""


class AgentGraph(BaseModel):
    """Normalized voice-agent flow IR for import/export and coverage hints."""

    id: str
    name: str = ""
    entry_node_id: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    global_nodes: list[GraphNode] = Field(default_factory=list)
    tools: list[GraphTool] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    # Platform call settings (language, voice, end-call phrases). Unlike ``raw``
    # this is serialized, so suite refills can read it back from disk.
    config: dict[str, Any] = Field(default_factory=dict)
    source_platform: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    def node_ids(self) -> list[str]:
        return [n.id for n in self.nodes]

    def tool_names(self) -> list[str]:
        return [t.name for t in self.tools]


def as_str_list(value: Any) -> list[str]:
    """Coerce a platform field into a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        return []
    return [str(v).strip() for v in items if str(v).strip()]


MAX_TOOL_PARAMS = 12

# Where each platform hides the callable's name, description and arg schema.
_NAME_KEYS = ("name", "tool_name", "function_name")
_DESC_KEYS = ("description", "desc", "instructions")
_SCHEMA_KEYS = ("parameters", "api_schema", "input_schema", "parameter_schema", "args")


def tool_param_names(schema: Any) -> list[str]:
    """Argument names from a JSON-Schema-ish object.

    Names only. The full schema is skipped on purpose — ``default``/``example``
    fields routinely hold real account ids, tokens and phone numbers.
    """
    if not isinstance(schema, dict):
        return []
    out: list[str] = []
    props = schema.get("properties")
    if isinstance(props, dict):
        out.extend(str(k) for k in props)
    else:
        # ElevenLabs nests under request_body_schema / query_params_schema.
        for value in schema.values():
            if isinstance(value, dict) and isinstance(value.get("properties"), dict):
                out.extend(str(k) for k in value["properties"])
    seen: set[str] = set()
    names: list[str] = []
    for raw in out:
        name = raw.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names[:MAX_TOOL_PARAMS]


def _first_str(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def graph_tool(raw: Any, *, node_id: str = "", fallback_name: str = "") -> GraphTool | None:
    """Normalize one platform tool payload into a :class:`GraphTool`.

    Deliberately lossy — it keeps the name, kind, description and argument
    names, and drops everything else. That is what keeps a tool's transport
    block (Vapi ``server.secret``, Retell ``url``, Bolna ``api_token``) out of
    the IR we persist and out of the brief we send to an LLM.

    Returns ``None`` when the payload has no usable name.
    """
    if not isinstance(raw, dict):
        return None
    fn = raw.get("function") if isinstance(raw.get("function"), dict) else {}
    kind = _first_str(raw, ("type",)) or _first_str(fn, ("type",))
    name = _first_str(fn, _NAME_KEYS) or _first_str(raw, _NAME_KEYS) or kind or fallback_name.strip()
    if not name:
        return None
    schema: Any = None
    for source in (fn, raw):
        for key in _SCHEMA_KEYS:
            if isinstance(source.get(key), dict):
                schema = source[key]
                break
        if schema is not None:
            break
    return GraphTool(
        name=name,
        type=kind,
        description=_first_str(fn, _DESC_KEYS) or _first_str(raw, _DESC_KEYS),
        parameters=tool_param_names(schema),
        node_id=node_id.strip(),
    )


def graph_tools(raw_tools: Any, *, node_id: str = "") -> list[GraphTool]:
    """Normalize a platform tool list, dropping unusable and duplicate entries.

    Accepts a JSON string as well — Bolna stores its function defs that way.
    """
    if isinstance(raw_tools, str):
        try:
            raw_tools = json.loads(raw_tools)
        except (TypeError, ValueError):
            return []
    if isinstance(raw_tools, dict):
        raw_tools = [raw_tools]
    if not isinstance(raw_tools, (list, tuple)):
        return []
    out: list[GraphTool] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_tools):
        tool = graph_tool(raw, node_id=node_id, fallback_name=f"tool_{i}")
        if tool is None or tool.name in seen:
            continue
        seen.add(tool.name)
        out.append(tool)
    return out


def graph_config(**values: Any) -> dict[str, Any]:
    """Build an AgentGraph.config, dropping keys the platform did not provide."""
    out: dict[str, Any] = {}
    for key, val in values.items():
        if val is None or val == "" or val == [] or val == {}:
            continue
        out[key] = val
    return out


__all__ = [
    "MAX_TOOL_PARAMS",
    "AgentGraph",
    "GraphEdge",
    "GraphNode",
    "GraphTool",
    "NodeType",
    "as_str_list",
    "graph_config",
    "graph_tool",
    "graph_tools",
    "tool_param_names",
]
