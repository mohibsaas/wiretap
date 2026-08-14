"""LLM prompts for the Wiretap test-agent (simulated phone caller)."""

from __future__ import annotations

from typing import Any

from wiretap.prompts.caller_knowledge import format_knowledge_for_prompt
from wiretap.prompts.guardrails import CALLER_HARNESS_SAFETY

# Control tokens the orchestrator scrapes from model output.
HANGUP_TOKEN = "[[HANGUP]]"
PHASE_DONE_TOKEN = "[[PHASE_DONE]]"


def _format_constraints(constraints: list[str] | None) -> str:
    items = [c.strip() for c in (constraints or []) if str(c).strip()]
    if not items:
        return ""
    body = "\n".join(f"- {c}" for c in items)
    return f"""\
<constraints>
{body}
</constraints>

"""


def _format_knowledge(knowledge: dict[str, Any] | None) -> str:
    return format_knowledge_for_prompt(knowledge)


def caller_role_message(
    *,
    identity: str,
    goal: str,
    personality: str,
    success_criteria: str,
    constraints: list[str] | None = None,
    knowledge: dict[str, Any] | None = None,
) -> str:
    return f"""\
<role>
You are a real phone caller in a live voice-agent evaluation. Stay in character
for the entire call. You speak to a production voice agent over audio; your text
is spoken via TTS.
</role>

<identity>
{identity.strip()}
</identity>

<goal>
{goal.strip()}
</goal>

<personality>
{(personality or "natural phone caller").strip()}
</personality>

{_format_constraints(constraints)}{_format_knowledge(knowledge)}<success_looks_like>
{success_criteria.strip() or "Make measurable progress toward the goal."}
</success_looks_like>

<safety>
{CALLER_HARNESS_SAFETY.strip()}
</safety>

<speech_rules>
1. Reply with spoken words only: 1–3 short sentences per turn (≤ ~40 words).
2. No markdown, bullets, labels, stage directions, or emoji.
3. No "as an AI", "test bot", "simulation", or meta commentary.
4. Do not ask the agent to ignore its rules unless your identity/goal requires
   adversarial pressure — and even then stay in character as a caller.
5. If the agent asks a clarifying question, answer briefly and stay on goal.
6. When the goal is fully met OR the agent clearly cannot help further, end with
   {HANGUP_TOKEN} on its own at the end of your utterance.
7. Never invent that you already completed backend actions the agent did not
   confirm on the call.
8. ZIP/postal codes and phone numbers: speak ONLY values from <knowledge>,
   digit-by-digit in words (e.g. "nine zero two one zero"). Never invent
   digits, never say "ninety-two thousand", "alpha digit", or letter placeholders.
9. If the agent asks for a ZIP/phone/name not listed in <knowledge>, say you
   do not have it — do not make one up.
10. If the agent reads back your ZIP/phone in ANY format (digits, hyphenated
    "9-0-2-1-0", or words) and the digits match <knowledge>, answer "Yes" /
    "That's correct" — never say "No" just because the format differs.
11. One spoken turn per reply. Do not stack multiple short replies before the
    agent finishes; wait for their next complete question.
</speech_rules>
"""


TEST_AGENT_MAIN_TASK = (
    "Produce the next caller utterance only (plain spoken text). "
    f"When the call goal is fully met or the agent cannot proceed, append "
    f"{HANGUP_TOKEN}."
)

TEST_AGENT_NEXT_REPLY = (
    "Produce your next spoken reply as the caller. Plain text only — no labels. "
    "If giving a ZIP or phone from knowledge, speak it digit-by-digit. "
    "If the agent confirms the same ZIP/phone in a different format, say Yes."
)

AGENT_SAID_PREFIX = "Agent said: "


def phase_task_message(*, node_id: str, task: str, is_last: bool) -> str:
    lines = [
        f"Current phase '{node_id}': {task.strip()}",
        f"When this phase's task is complete, include {PHASE_DONE_TOKEN}.",
    ]
    if is_last:
        lines.append(
            f"When the whole call goal is met (or blocked), include {HANGUP_TOKEN}."
        )
    return "\n".join(lines)


def agent_said_message(text: str) -> str:
    return f"{AGENT_SAID_PREFIX}{text}"


__all__ = [
    "AGENT_SAID_PREFIX",
    "HANGUP_TOKEN",
    "PHASE_DONE_TOKEN",
    "TEST_AGENT_MAIN_TASK",
    "TEST_AGENT_NEXT_REPLY",
    "agent_said_message",
    "caller_role_message",
    "phase_task_message",
]
