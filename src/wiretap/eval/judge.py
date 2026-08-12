"""LLM-as-judge. Suggestions only when the call fails."""

from __future__ import annotations

import json
from typing import Any

from wiretap.eval.transcript import transcript_text
from wiretap.models import JudgeResult, TurnRecord
from wiretap.providers.llm import complete


def judge_call(
    *,
    model: str,
    turns: list[TurnRecord],
    success_criteria: str,
    rubric: str,
) -> JudgeResult:
    prompt = f"""You are an eval judge for a voice-agent test call.
Success criteria: {success_criteria}
Rubric:
{rubric or "(use success criteria)"}

Transcript:
{transcript_text(turns)}

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
    raw = complete(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=600,
    )
    data = _parse_json(raw)
    passed = bool(data.get("passed", False))
    suggestions = data.get("suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = [str(suggestions)]
    suggestions = [str(s).strip() for s in suggestions if str(s).strip()]
    if passed:
        suggestions = []
    return JudgeResult(
        passed=passed,
        score=data.get("score"),
        reason=str(data.get("reason", raw)),
        suggestions=suggestions,
    )


def _parse_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        pass
    return {
        "passed": False,
        "score": None,
        "reason": f"Judge returned non-JSON: {raw[:200]}",
        "suggestions": [],
    }
