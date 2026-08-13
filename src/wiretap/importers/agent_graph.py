"""AgentGraph intermediate representation (data only — not executed)."""

from __future__ import annotations

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


class AgentGraph(BaseModel):
    """Normalized voice-agent flow IR for import/export and coverage hints."""

    id: str
    name: str = ""
    entry_node_id: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    global_nodes: list[GraphNode] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    source_platform: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict, exclude=True)

    def node_ids(self) -> list[str]:
        return [n.id for n in self.nodes]


__all__ = ["AgentGraph", "GraphEdge", "GraphNode", "NodeType"]
