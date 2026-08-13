"""LLM prompts for category-guided suite generation.

Structure follows Identity → Context → Rules → Output (system-prompt anatomy)
plus XML-tagged user payloads for clear section boundaries.
"""

from __future__ import annotations

import json
from typing import Any

SUITE_GENERATION_SYSTEM = """\
<role>
You are a senior voice-agent evaluation designer for Wiretap.
You write realistic phone-call test scenarios that a simulated caller will speak
live to a production voice agent (STT/TTS, turn-taking, short utterances).
</role>

<goal>
Produce mutually distinct scenarios for ONE eval category that stress the live
agent's behavior — not the test harness. Scenarios must be speakable on a phone.
</goal>

<context>
Wiretap runs a test agent that dials the live agent, speaks opening lines, and
continues turn-by-turn. An LLM judge later scores the transcript against each
scenario's success criteria and excludes list.
When <agent_brief> is present, ground identity/goal/say/success in that agent's
role, tools/flow nodes, and policies. Do not invent proprietary product facts
that contradict the brief.
</context>

<rules>
1. Output MUST be a single JSON array — no markdown fences, no commentary.
2. Generate exactly the requested count of objects.
3. Each object MUST use keys: name, identity, goal, say, success, excludes.
4. name: short human title (≤ 8 words), unique within the batch.
5. identity: who the caller is (one sentence, third person).
6. goal: what the caller wants by end of call (observable outcome).
7. say: first spoken line only — natural speech, ≤ 25 words, no stage directions.
8. success: judge-facing pass criteria — observable from transcript; avoid vague
   words like "good" or "helpful" without a concrete behavior.
9. excludes: list of banned substrings the live agent must not say (strings).
   Use [] unless the category needs policy red lines (compliance, adversarial).
10. Scenarios in one batch must differ in caller intent, pressure, or edge case —
    not just reword the same plot.
11. Prefer positive instructions in success ("Agent does X") over vague negatives.
12. Never put API keys, tokens, passwords, or real PII in any field.
13. Do not write scenarios that require the test agent to reveal it is a bot.
</rules>

<field_schema>
[
  {
    "name": "string",
    "identity": "string",
    "goal": "string",
    "say": "string",
    "success": "string",
    "excludes": ["string"]
  }
]
</field_schema>
"""


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
    ctx: dict[str, Any] = {
        "agent_name": agent_name,
        "purpose": purpose.strip() or "(none provided)",
        "category": category,
        "category_label": category_label,
        "category_description": category_description,
        "count": count,
        "few_shot_examples": few_shot_examples,
    }
    if agent_brief:
        ctx["agent_brief"] = agent_brief
    return ctx


def suite_generation_user_message(count: int, context: dict[str, Any]) -> str:
    brief = context.get("agent_brief")
    examples = context.get("few_shot_examples") or []
    parts = [
        "<instructions>",
        f"Generate exactly {count} distinct test cases for category "
        f"{context.get('category_label')!r} ({context.get('category')}).",
        f"Category intent: {context.get('category_description')}",
        f"Target agent name: {context.get('agent_name')}",
        f"Stated purpose: {context.get('purpose')}",
        "Return JSON array only.",
        "</instructions>",
        "",
        "<agent_brief>",
        json.dumps(brief, indent=2, ensure_ascii=False)
        if brief
        else "(not provided — use purpose + category only)",
        "</agent_brief>",
        "",
        "<few_shot_examples>",
        "Style and diversity reference only — do not copy names or plots verbatim.",
        json.dumps(examples, indent=2, ensure_ascii=False),
        "</few_shot_examples>",
    ]
    return "\n".join(parts)


def suite_generation_retry_user_message(
    *,
    need: int,
    category: str,
    agent_name: str,
    existing_names: list[str],
    context: dict[str, Any],
) -> str:
    brief = context.get("agent_brief")
    return "\n".join(
        [
            "<instructions>",
            f"Generate {need} MORE distinct test cases in category {category!r} "
            f"for agent {agent_name!r}.",
            "Do not reuse or paraphrase these names:",
            json.dumps(existing_names, ensure_ascii=False),
            "Return JSON array only.",
            "</instructions>",
            "",
            "<agent_brief>",
            json.dumps(brief, indent=2, ensure_ascii=False)
            if brief
            else "(not provided)",
            "</agent_brief>",
            "",
            "<prior_context>",
            json.dumps(
                {
                    "purpose": context.get("purpose"),
                    "category": context.get("category"),
                    "category_description": context.get("category_description"),
                },
                indent=2,
                ensure_ascii=False,
            ),
            "</prior_context>",
        ]
    )


__all__ = [
    "SUITE_GENERATION_SYSTEM",
    "suite_generation_context",
    "suite_generation_retry_user_message",
    "suite_generation_user_message",
]
