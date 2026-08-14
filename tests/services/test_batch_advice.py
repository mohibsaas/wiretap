"""Advisor runs after each fail/partial, not after the suite, not on passes."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from wiretap.eval.advisor import needs_attention
from wiretap.models import (
    JudgeResult,
    RuleResult,
    RunAdvice,
    SimulationArtifact,
    SuiteConfig,
    TurnRecord,
)
from wiretap.services.batches import BatchRecord, _refresh_advice


def _art(*, passed: bool, verdict: str, inconclusive: bool = False) -> SimulationArtifact:
    return SimulationArtifact(
        simulation_id=f"sim-{verdict}",
        suite_id="default",
        scenario_id=verdict,
        persona_id="p1",
        passed=passed,
        transcript=[TurnRecord(role="agent", text="hi")],
        judge=JudgeResult(
            passed=passed, score=0.2 if not passed else 0.9, verdict=verdict, reason="r"
        ),
        rules=RuleResult(passed=True),
        meta={"inconclusive": True} if inconclusive else {},
    )


def test_needs_attention_is_fail_or_partial_only() -> None:
    assert needs_attention(_art(passed=False, verdict="fail"))
    assert needs_attention(_art(passed=False, verdict="partial"))
    assert not needs_attention(_art(passed=True, verdict="pass"))
    assert not needs_attention(_art(passed=False, verdict="fail", inconclusive=True))


def test_refresh_skips_pass_and_inconclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"n": 0}

    async def _boom(*args: object, **kwargs: object) -> RunAdvice:
        called["n"] += 1
        raise AssertionError("advisor must not run")

    monkeypatch.setattr("wiretap.eval.advisor.advise_for_run", _boom)
    cfg = SuiteConfig(personas=[], scenarios=[])

    async def _run() -> None:
        lock = asyncio.Lock()
        batch = BatchRecord(batch_id="b", suite="default")
        passing = _art(passed=True, verdict="pass")
        batch.results.append(passing)
        await _refresh_advice(batch, cfg, "default", None, lock=lock, artifact=passing)
        incon = _art(passed=False, verdict="fail", inconclusive=True)
        batch.results.append(incon)
        await _refresh_advice(batch, cfg, "default", None, lock=lock, artifact=incon)
        assert batch.advice is None
        assert called["n"] == 0

    asyncio.run(_run())


def test_refresh_runs_after_fail_and_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []

    async def _fake(cfg, artifacts, *, suite_id: str, cwd=None) -> RunAdvice:
        seen.append([a.scenario_id for a in artifacts])
        return RunAdvice(summary="fix identity", findings=[], grounding="config")

    monkeypatch.setattr("wiretap.eval.advisor.advise_for_run", _fake)
    cfg = SuiteConfig(personas=[], scenarios=[])

    async def _run() -> None:
        lock = asyncio.Lock()
        batch = BatchRecord(batch_id="batch-fail", suite="default")
        fail = _art(passed=False, verdict="fail")
        batch.results.append(fail)
        await _refresh_advice(batch, cfg, "default", tmp_path, lock=lock, artifact=fail)
        assert batch.advice is not None
        assert batch.advice.summary == "fix identity"
        assert any(e.get("type") == "advice_ready" for e in batch.events)
        path = tmp_path / ".wiretap" / "evaluations" / "batch-fail.json"
        assert path.is_file()
        assert "fix identity" in path.read_text(encoding="utf-8")

        partial = _art(passed=False, verdict="partial")
        batch.results.append(partial)
        await _refresh_advice(batch, cfg, "default", tmp_path, lock=lock, artifact=partial)
        assert seen == [["fail"], ["fail", "partial"]]

    asyncio.run(_run())
