"""Meta-check and JUnit report tests."""

from pathlib import Path

from wiretap.eval.meta import check_caller_contract
from wiretap.models import (
    JudgeResult,
    Persona,
    RuleResult,
    SimulationArtifact,
    TurnRecord,
)
from wiretap.report import write_junit_report


def test_caller_contract_ok() -> None:
    p = Persona(id="p", identity="x", goal="y")
    turns = [TurnRecord(role="user", text="I want to cancel please")]
    assert check_caller_contract(persona=p, turns=turns) == []


def test_junit_writes(tmp_path: Path) -> None:
    arts = [
        SimulationArtifact(
            suite_id="s",
            scenario_id="a",
            persona_id="p",
            passed=True,
            transcript=[],
            judge=JudgeResult(passed=True, reason="ok", suggestions=[]),
            rules=RuleResult(passed=True),
        )
    ]
    path = write_junit_report(arts, tmp_path / "out.xml")
    text = path.read_text(encoding="utf-8")
    assert "testcase" in text
    assert 'failures="0"' in text


def test_junit_inconclusive_is_skipped(tmp_path: Path) -> None:
    arts = [
        SimulationArtifact(
            suite_id="s",
            scenario_id="bad_caller",
            persona_id="p",
            passed=False,
            transcript=[],
            judge=JudgeResult(
                passed=False,
                reason="Inconclusive: caller broke contract",
                suggestions=[],
            ),
            rules=RuleResult(passed=True),
            meta={"inconclusive": True},
        )
    ]
    text = write_junit_report(arts, tmp_path / "skip.xml").read_text(encoding="utf-8")
    assert 'failures="0"' in text
    assert 'skipped="1"' in text
    assert "simulator_invalid" in text
