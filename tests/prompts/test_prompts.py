"""Prompt package imports and builders."""

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


def test_category_catalog_keys() -> None:
    assert "task" in CATEGORY_CATALOG
    assert set(DEFAULT_CATEGORIES) <= set(CATEGORY_CATALOG)


def test_judge_prompt_includes_transcript() -> None:
    text = judge_call_prompt(
        success_criteria="Done",
        rubric="Be fair",
        transcript="Caller: hi\nAgent: hello",
    )
    assert "Done" in text
    assert "Caller: hi" in text
    assert "passed" in text


def test_caller_role_and_phase() -> None:
    role = caller_role_message(
        identity="A customer",
        goal="Cancel",
        personality="calm",
        success_criteria="Cancelled",
    )
    assert "A customer" in role
    assert "[[HANGUP]]" in TEST_AGENT_MAIN_TASK
    phase = phase_task_message(node_id="verify", task="Confirm ID", is_last=True)
    assert "verify" in phase
    assert "[[PHASE_DONE]]" in phase
    assert "[[HANGUP]]" in phase


def test_suite_generation_user_message() -> None:
    msg = suite_generation_user_message(3, {"category": "task", "count": 3})
    assert "exactly 3" in msg
    assert "task" in msg
    assert SUITE_GENERATION_SYSTEM.startswith("You design")
