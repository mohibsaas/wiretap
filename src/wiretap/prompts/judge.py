"""LLM prompt for the call eval judge."""

from __future__ import annotations


def judge_call_prompt(
    *,
    success_criteria: str,
    rubric: str,
    transcript: str,
) -> str:
    return f"""You are an eval judge for a voice-agent test call.
Success criteria: {success_criteria}
Rubric:
{rubric or "(use success criteria)"}

Transcript:
{transcript}

Respond with JSON only:
{{
  "passed": bool,
  "score": number|null,
  "reason": string,
  "suggestions": [string, ...]
}}

If passed is true, suggestions must be [].
If passed is false, give 1-5 concrete improvements for the live agent.
Do not invent secrets or tool IDs.
"""
