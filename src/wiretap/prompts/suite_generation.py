"""LLM prompts for category-guided suite generation."""

from __future__ import annotations

import json
from typing import Any

SUITE_GENERATION_SYSTEM = (
    "You design voice-agent evaluation scenarios. "
    "Return ONLY a JSON array (no prose). Each item must have keys: "
    "name, identity, goal, say, success, excludes. "
    "name: short human title. identity: who the caller is. "
    "goal: what the caller wants. say: first spoken line. "
    "success: judge criteria for a pass. excludes: optional list of "
    "banned substrings the agent must not say (else []). "
    "Scenarios must be realistic phone conversations and mutually distinct."
    "\n\n"
    "Grounding rules:\n"
    "- When agent_brief is present, ground every scenario in it — its stated "
    "role, goals, constraints, tools and flow. Task, compliance and factual "
    "scenarios must probe what this agent actually does.\n"
    "- Never invent tools, policies, prices or capabilities that contradict "
    "the brief. If a detail is not in the brief, have the caller ask for it "
    "rather than asserting it.\n"
    "- agent_brief.irreversible_tools are side effects the caller cannot undo; "
    "they are good targets for confirmation and escalation scenarios.\n"
    "- Never put any agent_brief.end_call_phrases value, or a farewell, in "
    "'say'. That hangs up the call and scores as an agent failure.\n"
    "- Write 'say' in agent_brief.language when one is given.\n"
    "- When agent_brief is absent or empty, fall back to purpose plus the "
    "category guidance."
)


def suite_generation_context(
    *,
    agent_name: str,
    purpose: str,
    category: str,
    category_label: str,
    category_description: str,
    count: int,
    few_shot_examples: list[dict[str, Any]],
    agent_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "agent_name": agent_name,
        "purpose": purpose.strip() or "(none provided)",
        "category": category,
        "category_label": category_label,
        "category_description": category_description,
        "count": count,
        "few_shot_examples": few_shot_examples,
    }
    # Sanitized upstream in services.agent_brief; omitted entirely when empty so
    # the model sees no half-filled brief to over-read.
    context["agent_brief"] = agent_brief or {}
    return context


def suite_generation_user_message(count: int, context: dict[str, Any]) -> str:
    return (
        f"Generate exactly {count} test cases for this voice agent.\n"
        + json.dumps(context, indent=2)
    )


def suite_generation_retry_user_message(
    *,
    need: int,
    category: str,
    agent_name: str,
    existing_names: list[str],
    context: dict[str, Any],
) -> str:
    return (
        f"Generate {need} MORE distinct test cases in category "
        f"{category!r} for agent {agent_name!r}. "
        "Do not repeat these names: "
        + json.dumps(existing_names)
        + "\nContext: "
        + json.dumps(context, indent=2)
    )
