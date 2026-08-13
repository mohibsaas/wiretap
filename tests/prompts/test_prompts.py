"""Prompt package imports and builders."""

from wiretap.importers.agent_graph import AgentGraph, GraphEdge, GraphNode, NodeType
from wiretap.prompts import (
    CATEGORY_CATALOG,
    DEFAULT_CATEGORIES,
    SUITE_GENERATION_SYSTEM,
    TEST_AGENT_MAIN_TASK,
    agent_brief_from_graph,
    agent_brief_from_purpose_only,
    caller_role_message,
    judge_call_prompt,
    sanitize_text,
    suite_generation_user_message,
)
from wiretap.prompts.test_agent import phase_task_message


def test_category_catalog_keys() -> None:
    assert "task" in CATEGORY_CATALOG
    assert set(DEFAULT_CATEGORIES) <= set(CATEGORY_CATALOG)
    # Diverse few-shots: at least two examples for core categories
    for key in DEFAULT_CATEGORIES:
        assert len(CATEGORY_CATALOG[key]["examples"]) >= 2


def test_judge_prompt_includes_transcript() -> None:
    text = judge_call_prompt(
        success_criteria="Done",
        rubric="Be fair",
        transcript="Caller: hi\nAgent: hello",
    )
    assert "Done" in text
    assert "Caller: hi" in text
    assert "passed" in text
    assert "<transcript>" in text
    assert "<scoring_guide>" in text


def test_caller_role_and_phase() -> None:
    role = caller_role_message(
        identity="A customer",
        goal="Cancel",
        personality="calm",
        success_criteria="Cancelled",
    )
    assert "A customer" in role
    assert "<speech_rules>" in role
    assert "[[HANGUP]]" in TEST_AGENT_MAIN_TASK
    phase = phase_task_message(node_id="verify", task="Confirm ID", is_last=True)
    assert "verify" in phase
    assert "[[PHASE_DONE]]" in phase
    assert "[[HANGUP]]" in phase


def test_suite_generation_user_message() -> None:
    msg = suite_generation_user_message(
        3,
        {
            "category": "task",
            "category_label": "Task",
            "category_description": "Complete tasks",
            "count": 3,
            "agent_name": "booker",
            "purpose": "Book appointments",
            "few_shot_examples": [],
            "agent_brief": {"agent_display_name": "booker"},
        },
    )
    assert "exactly 3" in msg
    assert "<agent_brief>" in msg
    assert "booker" in msg
    assert "<role>" in SUITE_GENERATION_SYSTEM


def test_agent_brief_sanitizes_secrets() -> None:
    dirty = "Use api_key: sk-live-abc123 and continue"
    assert "[REDACTED]" in sanitize_text(dirty)
    assert "sk-live-abc123" not in sanitize_text(dirty)

    graph = AgentGraph(
        id="a1",
        name="Support",
        entry_node_id="n1",
        source_platform="vapi",
        nodes=[
            GraphNode(
                id="n1",
                type=NodeType.CONVERSATION,
                name="Greet",
                prompt="Help callers. password: hunter2",
            )
        ],
        edges=[GraphEdge(id="e1", source="n1", target="n1", label="loop")],
    )
    brief = agent_brief_from_graph(graph, purpose="Support bot")
    assert brief["agent_display_name"] == "Support"
    assert brief["flow_nodes"]
    blob = str(brief)
    assert "hunter2" not in blob
    assert "[REDACTED]" in blob or "password" in blob.lower()

    minimal = agent_brief_from_purpose_only(
        agent_name="x", purpose="Book demos"
    )
    assert minimal["stated_purpose"] == "Book demos"
