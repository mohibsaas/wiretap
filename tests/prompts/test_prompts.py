"""Prompt package imports and builders."""

from wiretap.importers.agent_graph import AgentGraph, GraphEdge, GraphNode, NodeType
from wiretap.prompts import (
    CATEGORY_CATALOG,
    DEFAULT_CATEGORIES,
    SUITE_GENERATION_SYSTEM,
    TEST_AGENT_MAIN_TASK,
    caller_role_message,
    judge_call_prompt,
    suite_generation_user_message,
)
from wiretap.prompts.test_agent import phase_task_message
from wiretap.services.agent_brief import (
    agent_brief_from_graph,
    agent_brief_from_purpose_only,
    sanitize_text,
)


def test_category_catalog_keys() -> None:
    assert "task" in CATEGORY_CATALOG
    assert set(DEFAULT_CATEGORIES) <= set(CATEGORY_CATALOG)
    # Diverse few-shots: at least two examples for core categories
    for key in DEFAULT_CATEGORIES:
        assert len(CATEGORY_CATALOG[key]["examples"]) >= 2


def test_judge_prompt_includes_goal_and_transcript() -> None:
    text = judge_call_prompt(
        success_criteria="Confirm company and start intake",
        goal="Reach the right concrete company",
        scenario_name="Anxious first-time caller",
        rubric="Be fair to STT noise",
        transcript="Caller: hi\nAgent: hello",
        fail_below=0.5,
        pass_at=0.7,
    )
    assert "Confirm company and start intake" in text
    assert "Reach the right concrete company" in text
    assert "Anxious first-time caller" in text
    assert "Caller: hi" in text
    assert "<transcript>" in text
    assert "<caller_goal>" in text
    assert "<success_criteria>" in text
    assert "partial" in text
    assert '"score"' in text
    assert "task_completion" not in text
    assert "<metrics>" not in text


def test_judge_prompt_includes_tool_evidence_when_captured() -> None:
    text = judge_call_prompt(
        success_criteria="Book it",
        rubric="",
        transcript="Caller: hi",
        tool_report="Expected for this scenario: book_appointment",
    )
    assert "\n<tool_evidence>" in text
    assert "<tool_rules>" in text
    assert "book_appointment" in text


def test_judge_prompt_omits_tool_evidence_when_unobservable() -> None:
    """An empty report must remove the block, not render an empty one — the
    judge would otherwise fail the agent for a tool we could not observe."""
    text = judge_call_prompt(
        success_criteria="Book it",
        rubric="",
        transcript="Caller: hi",
        tool_report="",
    )
    assert "\n<tool_evidence>" not in text
    assert "<tool_rules>" not in text


def test_caller_role_and_phase() -> None:
    role = caller_role_message(
        identity="A customer",
        goal="Cancel",
        personality="calm",
        success_criteria="Cancelled",
        constraints=["Do not reveal you are a test bot"],
        knowledge={"email": "caller@example.com"},
    )
    assert "A customer" in role
    assert "<speech_rules>" in role
    assert "<safety>" in role
    assert "<constraints>" in role
    assert "Do not reveal you are a test bot" in role
    assert "<knowledge>" in role
    assert "caller@example.com" in role
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
