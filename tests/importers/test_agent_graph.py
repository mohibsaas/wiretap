"""AgentGraph IR tests."""

from wiretap.importers import AgentGraph, GraphEdge, GraphNode, NodeType


def test_agent_graph_roundtrip() -> None:
    g = AgentGraph(
        id="a1",
        name="demo",
        entry_node_id="main",
        nodes=[
            GraphNode(id="main", type=NodeType.CONVERSATION, prompt="hi"),
            GraphNode(id="end", type=NodeType.END),
        ],
        edges=[GraphEdge(id="e1", source="main", target="end")],
        source_platform="vapi",
    )
    data = g.model_dump(mode="json")
    g2 = AgentGraph.model_validate(data)
    assert g2.entry_node_id == "main"
    assert g2.node_ids() == ["main", "end"]
