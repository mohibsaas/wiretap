"""Importer suite builder tests."""

from wiretap.importers.suite_builder import suite_from_prompt
from wiretap.importers import AgentGraph, GraphNode, NodeType


def test_suite_from_prompt() -> None:
    suite = suite_from_prompt(
        platform="vapi",
        agent_id="asst_1",
        agent_name="Support",
        system_prompt="You help users cancel subscriptions and explain refunds.",
        first_message="Hi I want to cancel",
    )
    assert suite.agent.platform == "vapi"
    assert suite.personas[0].id == "imported_caller"
    assert suite.scenarios[0].beats[0].say


def test_suite_adds_flow_coverage() -> None:
    graph = AgentGraph(
        id="x",
        entry_node_id="a",
        nodes=[
            GraphNode(id="a", type=NodeType.CONVERSATION),
            GraphNode(id="b", type=NodeType.CONVERSATION),
            GraphNode(id="c", type=NodeType.END),
        ],
    )
    suite = suite_from_prompt(
        platform="retell",
        agent_id="agent_1",
        agent_name="Bot",
        system_prompt="Book appointments",
        graph=graph,
    )
    assert any(s.id == "flow_coverage" for s in suite.scenarios)
