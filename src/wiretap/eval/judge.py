"""LLM-as-judge. Suggestions only when the call fails."""

from __future__ import annotations

import json
from typing import Any

from wiretap.eval.transcript import transcript_text
from wiretap.models import JudgeResult, TurnRecord
from wiretap.prompts.judge import judge_call_prompt
from wiretap.providers.llm import complete


def judge_call(
    *,
    model: str,
    turns: list[TurnRecord],
    success_criteria: str,
    rubric: str,
) -> JudgeResult:
    prompt = judge_call_prompt(
        success_criteria=success_criteria,
        rubric=rubric,
        transcript=transcript_text(turns),
    )
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
