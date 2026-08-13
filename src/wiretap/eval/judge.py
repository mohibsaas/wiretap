"""LLM-as-judge — goal / success-criteria match score.

One completion returns a 0–1 match percentage. Wiretap maps bands:
  score < fail_below  → fail
  fail_below ≤ score < pass_at → partial
  score ≥ pass_at → pass

When tool calls were observable, they are included as evidence in the prompt.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from wiretap.eval.tools import tool_report_text
from wiretap.eval.transcript import transcript_text
from wiretap.models import JudgeConfig, JudgeResult, ToolCallRecord, TurnRecord
from wiretap.prompts.judge import judge_call_prompt
from wiretap.providers.llm import acomplete

DEFAULT_PASS_THRESHOLD = 0.7
DEFAULT_FAIL_BELOW = 0.5
JudgeVerdict = Literal["fail", "partial", "pass"]


async def judge_call(
    *,
    model: str,
    turns: list[TurnRecord],
    success_criteria: str,
    rubric: str = "",
    goal: str = "",
    scenario_name: str = "",
    pass_threshold: float | None = None,
    judge_config: JudgeConfig | None = None,
    expected_tools: list[str] | None = None,
    tool_calls: list[ToolCallRecord] | None = None,
    tool_capture: str = "unsupported",
) -> JudgeResult:
    base = judge_config or JudgeConfig()
    pass_at = _clamp(
        pass_threshold if pass_threshold is not None else base.pass_threshold,
        default=DEFAULT_PASS_THRESHOLD,
    )
    fail_below = _clamp(base.fail_below, default=DEFAULT_FAIL_BELOW)
    if fail_below > pass_at:
        fail_below = min(fail_below, pass_at)

    prompt = judge_call_prompt(
        success_criteria=success_criteria,
        goal=goal,
        scenario_name=scenario_name,
        rubric=rubric,
        transcript=transcript_text(turns),
        fail_below=fail_below,
        pass_at=pass_at,
        tool_report=tool_report_text(
            expected=expected_tools or [],
            actual=tool_calls or [],
            capture=tool_capture,
        ),
    )
    raw = await acomplete(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=800,
    )
    data = _parse_json(raw)
    score = _coerce_score(data.get("score"))
    if score is None:
        # Legacy multi-rubric / alias keys
        score = _coerce_score(data.get("overall_score"))
    if score is None:
        score = 0.0

    verdict = verdict_for_score(score, fail_below=fail_below, pass_at=pass_at)
    passed = verdict == "pass"

    suggestions = data.get("suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = [str(suggestions)]
    suggestions = [str(s).strip() for s in suggestions if str(s).strip()]
    if passed:
        suggestions = []

    reason = str(data.get("reason") or "").strip()
    if not reason:
        reason = f"Judge returned non-JSON or empty reason: {raw[:200]}"

    return JudgeResult(
        passed=passed,
        score=score,
        verdict=verdict,
        reason=reason,
        suggestions=suggestions,
        metrics=[],
        pass_mode="goal_match",
        fail_below=fail_below,
        pass_at=pass_at,
    )


def verdict_for_score(
    score: float,
    *,
    fail_below: float = DEFAULT_FAIL_BELOW,
    pass_at: float = DEFAULT_PASS_THRESHOLD,
) -> JudgeVerdict:
    """Map a 0–1 goal-match score onto fail / partial / pass."""
    s = _clamp(score, default=0.0)
    lo = _clamp(fail_below, default=DEFAULT_FAIL_BELOW)
    hi = _clamp(pass_at, default=DEFAULT_PASS_THRESHOLD)
    if lo > hi:
        lo = hi
    if s < lo:
        return "fail"
    if s < hi:
        return "partial"
    return "pass"


def _clamp(value: float, *, default: float) -> float:
    try:
        t = float(value)
    except (TypeError, ValueError):
        return default
    if t != t:  # NaN
        return default
    return min(1.0, max(0.0, t))


def _coerce_score(raw: object) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return None
    if score != score:
        return None
    # Allow judges that return 0–100 by mistake.
    if score > 1.0 and score <= 100.0:
        score = score / 100.0
    return min(1.0, max(0.0, score))


def _parse_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        pass
    return {
        "score": None,
        "reason": f"Judge returned non-JSON: {raw[:200]}",
        "suggestions": [],
    }


__all__ = [
    "DEFAULT_FAIL_BELOW",
    "DEFAULT_PASS_THRESHOLD",
    "judge_call",
    "verdict_for_score",
]
