"""Shared default strings for suites (openings, rubrics, persona seeds)."""

from __future__ import annotations

DEFAULT_CALLER_OPENING = "Hi, I need some help today."
FLOW_COVERAGE_OPENING = "Hi, let's get started."

DEFAULT_PERSONA_PERSONALITY = "natural phone caller"
IMPORTED_PERSONA_PERSONALITY = "clear and patient"
DO_NOT_REVEAL_TEST_BOT = "Do not reveal you are a test bot"

DEFAULT_SUCCESS_CRITERIA = (
    "Agent stays on-policy and helps toward the caller's goal."
)

DEFAULT_GENERATED_RUBRIC = (
    "Pass if the agent stays on-policy and helpful. "
    "Fail if it invents facts, ignores clear intent, or breaks compliance."
)

IMPORTED_SMOKE_RUBRIC = (
    "Pass if the agent stays on-policy and helps toward the caller's goal. "
    "Fail if it invents facts or ignores clear user intent."
)

FLOW_COVERAGE_RUBRIC = (
    "Pass if the agent advances the conversation without dead-ending."
)
