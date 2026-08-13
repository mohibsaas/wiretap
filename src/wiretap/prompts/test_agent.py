"""LLM prompts for the wiretap test-agent (fake caller) orchestrator."""

from __future__ import annotations


def caller_role_message(
    *,
    identity: str,
    goal: str,
    personality: str,
    success_criteria: str,
) -> str:
    return (
        "You are a phone caller in a voice-agent test. Stay in character. "
        "Short spoken replies only (1-3 sentences). No markdown.\n"
        f"Identity: {identity}\n"
        f"Goal: {goal}\n"
        f"Personality: {personality or 'neutral'}\n"
        f"Success looks like: {success_criteria}"
    )


TEST_AGENT_MAIN_TASK = (
    "Produce the next caller utterance. "
    "When the goal is fully met, include [[HANGUP]]."
)

TEST_AGENT_NEXT_REPLY = "Produce your next spoken reply as the caller. Text only."

AGENT_SAID_PREFIX = "Agent said: "


def phase_task_message(*, node_id: str, task: str, is_last: bool) -> str:
    done_hint = "When this phase is complete, include [[PHASE_DONE]]. "
    if is_last:
        done_hint += "When the whole call goal is met, include [[HANGUP]]."
    return f"Current phase '{node_id}': {task}\n{done_hint}"


def agent_said_message(text: str) -> str:
    return f"{AGENT_SAID_PREFIX}{text}"
