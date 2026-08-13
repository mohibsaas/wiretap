"""Provider concurrency caps and goal-match judge bands."""

from __future__ import annotations

import asyncio
import json

import pytest

from wiretap.eval.concurrency import provider_concurrency_cap, resolve_concurrency
from wiretap.eval.judge import judge_call, verdict_for_score
from wiretap.models import JudgeConfig, TurnRecord


def test_retell_cap_clamps() -> None:
    assert provider_concurrency_cap(transport="webrtc", platform="retell") == 2
    conc, note = resolve_concurrency(8, transport="webrtc", platform="retell")
    assert conc == 2
    assert note and "clamped" in note


def test_force_concurrency_allows_high() -> None:
    conc, note = resolve_concurrency(
        6, transport="webrtc", platform="retell", force=True
    )
    assert conc == 6
    assert note and "forcing" in note


def test_pstn_clamps_to_single_call() -> None:
    assert provider_concurrency_cap(transport="pstn", platform="retell") == 1
    conc, note = resolve_concurrency(4, transport="pstn", platform="retell")
    assert conc == 1
    assert note and "clamped" in note
    conc, note = resolve_concurrency(1, transport="pstn", platform="retell")
    assert conc == 1
    assert note is None


def test_pstn_cap_survives_force() -> None:
    conc, note = resolve_concurrency(4, transport="pstn", platform="retell", force=True)
    assert conc == 1
    assert note and "clamped" in note


def test_text_allows_higher() -> None:
    conc, note = resolve_concurrency(10, transport="text", platform="custom")
    assert conc == 10
    assert note is None


def _turns() -> list[TurnRecord]:
    return [
        TurnRecord(role="agent", text="hi"),
        TurnRecord(role="user", text="hello"),
    ]


def test_verdict_bands() -> None:
    assert verdict_for_score(0.49) == "fail"
    assert verdict_for_score(0.5) == "partial"
    assert verdict_for_score(0.69) == "partial"
    assert verdict_for_score(0.7) == "pass"
    assert verdict_for_score(1.0) == "pass"


def test_goal_match_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "score": 0.82,
        "reason": "Caller goal met; intake completed.",
        "suggestions": [],
    }

    async def _fake(**kwargs: object) -> str:
        return json.dumps(payload)

    monkeypatch.setattr("wiretap.eval.judge.acomplete", _fake)
    result = asyncio.run(
        judge_call(
            model="gpt-4o-mini",
            turns=_turns(),
            success_criteria="Confirm company and start intake",
            goal="Reach the right concrete company",
            scenario_name="Anxious first-time caller",
            judge_config=JudgeConfig(),
        )
    )
    assert result.passed is True
    assert result.verdict == "pass"
    assert result.score == 0.82
    assert result.metrics == []
    assert result.suggestions == []


def test_goal_match_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "score": 0.58,
        "reason": "Partial progress; no next steps given.",
        "suggestions": ["Outline next steps clearly."],
    }

    async def _fake(**kwargs: object) -> str:
        return json.dumps(payload)

    monkeypatch.setattr("wiretap.eval.judge.acomplete", _fake)
    result = asyncio.run(
        judge_call(
            model="gpt-4o-mini",
            turns=_turns(),
            success_criteria="De-escalate and give next steps",
            goal="Get an update on my project",
        )
    )
    assert result.passed is False
    assert result.verdict == "partial"
    assert result.score == 0.58
    assert result.suggestions == ["Outline next steps clearly."]


def test_goal_match_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "score": 0.24,
        "reason": "Agent ignored the caller goal.",
        "suggestions": ["Address the stated goal first."],
    }

    async def _fake(**kwargs: object) -> str:
        return json.dumps(payload)

    monkeypatch.setattr("wiretap.eval.judge.acomplete", _fake)
    result = asyncio.run(
        judge_call(
            model="gpt-4o-mini",
            turns=_turns(),
            success_criteria="Help with patio intake",
            goal="Book a patio estimate",
        )
    )
    assert result.passed is False
    assert result.verdict == "fail"
    assert result.score == 0.24


def test_score_as_percent_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(**kwargs: object) -> str:
        return '{"score": 75, "reason": "percent style", "suggestions": []}'

    monkeypatch.setattr("wiretap.eval.judge.acomplete", _fake)
    result = asyncio.run(
        judge_call(
            model="gpt-4o-mini",
            turns=_turns(),
            success_criteria="Greet",
            pass_threshold=0.7,
        )
    )
    assert result.score == 0.75
    assert result.verdict == "pass"
    assert result.passed is True


def test_legacy_overall_score_key(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(**kwargs: object) -> str:
        return (
            '{"overall_score": 0.4, "reason": "legacy key", '
            '"suggestions": ["Try again"]}'
        )

    monkeypatch.setattr("wiretap.eval.judge.acomplete", _fake)
    result = asyncio.run(
        judge_call(
            model="gpt-4o-mini",
            turns=_turns(),
            success_criteria="Greet",
        )
    )
    assert result.score == 0.4
    assert result.verdict == "fail"
