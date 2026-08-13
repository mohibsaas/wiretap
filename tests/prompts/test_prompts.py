"""Prompt package imports and builders."""

from wiretap.prompts import (
    CATEGORY_CATALOG,
    DEFAULT_CATEGORIES,
    SUITE_GENERATION_SYSTEM,
    TEST_AGENT_MAIN_TASK,
    caller_role_message,
    judge_call_prompt,
    suite_generation_context,
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
            "agent_brief": {"agent_name": "booker"},
        },
    )
    assert "exactly 3" in msg
    assert "<agent_brief>" in msg
    assert "booker" in msg
    assert "<role>" in SUITE_GENERATION_SYSTEM
    # Brief keys the grounding rules reference must be named in the prompt.
    assert "irreversible_tools" in SUITE_GENERATION_SYSTEM
    assert "end_call_phrases" in SUITE_GENERATION_SYSTEM


def test_suite_generation_context_without_brief() -> None:
    """No brief means an empty one, never a partially filled one."""
    context = suite_generation_context(
        agent_name="booker",
        purpose="",
        category="task",
        category_label="Task",
        category_description="Complete tasks",
        count=2,
        few_shot_examples=[],
    )
    assert context["agent_brief"] == {}
    assert context["purpose"] == "(none provided)"
    assert "(not provided" in suite_generation_user_message(2, context)
