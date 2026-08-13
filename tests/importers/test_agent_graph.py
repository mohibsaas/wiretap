"""AgentGraph IR tests."""

import json

from wiretap.importers import AgentGraph, GraphEdge, GraphNode, GraphTool, NodeType
from wiretap.importers.agent_graph import (
    MAX_TOOL_PARAMS,
    as_str_list,
    graph_config,
    graph_tool,
    graph_tools,
    tool_param_names,
)


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


def test_config_survives_json_roundtrip() -> None:
    """Unlike raw, config must persist — refills read it back from disk."""
    g = AgentGraph(
        id="a1",
        entry_node_id="main",
        config=graph_config(language="en", end_call_phrases=["goodbye"]),
        raw={"dropped": True},
    )
    g2 = AgentGraph.model_validate_json(g.model_dump_json())

    assert g2.config == {"language": "en", "end_call_phrases": ["goodbye"]}
    assert g2.raw == {}


def test_graph_config_drops_empty_values() -> None:
    assert graph_config(language="en", voice_id=None, end_call_phrases=[]) == {"language": "en"}
    assert graph_config() == {}


def test_as_str_list_coerces() -> None:
    assert as_str_list("bye") == ["bye"]
    assert as_str_list(["bye", " ", "later"]) == ["bye", "later"]
    assert as_str_list(None) == []
    assert as_str_list({"a": 1}) == []


def test_graph_tool_reads_vapi_shape() -> None:
    tool = graph_tool(
        {
            "type": "function",
            "function": {
                "name": "book_appointment",
                "description": "Books a slot",
                "parameters": {"properties": {"date": {}, "time": {}}},
            },
        }
    )

    assert tool is not None
    assert tool.name == "book_appointment"
    assert tool.type == "function"
    assert tool.description == "Books a slot"
    assert tool.parameters == ["date", "time"]


def test_graph_tool_reads_retell_shape() -> None:
    tool = graph_tool(
        {
            "type": "custom",
            "name": "lookup_order",
            "description": "Finds an order",
            "parameters": {"properties": {"order_id": {}}},
        },
        node_id="intake",
    )

    assert tool is not None
    assert tool.name == "lookup_order"
    assert tool.type == "custom"
    assert tool.node_id == "intake"
    assert tool.parameters == ["order_id"]


def test_graph_tool_falls_back_to_type_as_name() -> None:
    """Retell built-ins like end_call carry a type but no name."""
    tool = graph_tool({"type": "end_call"})

    assert tool is not None
    assert tool.name == "end_call"
    assert tool.type == "end_call"


def test_graph_tool_drops_transport_and_credentials() -> None:
    """A tool payload's server block must never reach the IR."""
    tool = graph_tool(
        {
            "type": "function",
            "function": {"name": "charge_card", "parameters": {"properties": {"amount": {}}}},
            "url": "https://api.internal.example.com/charge",
            "api_token": "sk_live_abcdef1234567890",
            "server": {
                "url": "https://hooks.example.com/vapi",
                "secret": "shhh-shared-secret",
                "headers": {"Authorization": "Bearer tok_abc123"},
            },
        }
    )

    assert tool is not None
    assert tool.name == "charge_card"
    blob = tool.model_dump_json()
    for leaked in (
        "shhh-shared-secret",
        "tok_abc123",
        "sk_live_abcdef1234567890",
        "hooks.example.com",
        "api.internal.example.com",
    ):
        assert leaked not in blob


def test_tool_param_names_skips_schema_values() -> None:
    """default/example values routinely hold real ids — names only."""
    names = tool_param_names(
        {
            "properties": {
                "account_id": {"type": "string", "default": "acct_1H8sample"},
                "pin": {"type": "string", "example": "4821"},
            }
        }
    )

    assert names == ["account_id", "pin"]


def test_tool_param_names_reads_nested_elevenlabs_schema() -> None:
    names = tool_param_names(
        {
            "url": "https://example.com/hook",
            "request_body_schema": {"properties": {"zip_code": {}}},
            "query_params_schema": {"properties": {"lang": {}}},
        }
    )

    assert names == ["zip_code", "lang"]


def test_tool_param_names_caps_and_dedupes() -> None:
    schema = {"properties": {f"p{i}": {} for i in range(MAX_TOOL_PARAMS + 5)}}

    assert len(tool_param_names(schema)) == MAX_TOOL_PARAMS
    assert tool_param_names({"properties": {}}) == []
    assert tool_param_names(None) == []
    assert tool_param_names("nope") == []


def test_graph_tools_parses_json_string() -> None:
    """Bolna stores its function defs as a JSON string."""
    tools = graph_tools(json.dumps([{"name": "transfer_call", "description": "Hand off"}]))

    assert [t.name for t in tools] == ["transfer_call"]


def test_graph_tools_dedupes_and_drops_junk() -> None:
    tools = graph_tools(
        [
            {"name": "a"},
            {"name": "a"},
            "not-a-dict",
            None,
            {},
            {"name": "b"},
        ]
    )

    assert [t.name for t in tools] == ["a", "tool_4", "b"]
    assert graph_tools(None) == []
    assert graph_tools("{oops") == []


def test_graph_tools_survives_disk_roundtrip() -> None:
    graph = AgentGraph(
        id="a1",
        entry_node_id="main",
        tools=[GraphTool(name="book", type="custom", parameters=["date"], node_id="intake")],
    )
    loaded = AgentGraph.model_validate_json(graph.model_dump_json())

    assert loaded.tool_names() == ["book"]
    assert loaded.tools[0].parameters == ["date"]
    assert loaded.tools[0].node_id == "intake"
