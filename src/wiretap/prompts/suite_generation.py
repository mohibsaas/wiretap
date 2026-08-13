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
) -> dict[str, Any]:
    return {
        "agent_name": agent_name,
        "purpose": purpose.strip() or "(none provided)",
        "category": category,
        "category_label": category_label,
        "category_description": category_description,
        "count": count,
        "few_shot_examples": few_shot_examples,
    }


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
