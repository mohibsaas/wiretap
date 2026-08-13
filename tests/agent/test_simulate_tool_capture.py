"""Tool capture on a platform that cannot report tool calls.

The text stub has no backend to ask, so the artifact must say "unobservable"
rather than leaving an empty list that reads as "the agent called no tools".
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from wiretap.agent.simulate import simulate_scenario
from wiretap.models import (
    AgentTarget,
    ModelSlots,
    Persona,
    Scenario,
    SuiteConfig,
    TransportKind,
)


def _suite() -> SuiteConfig:
    return SuiteConfig(
        agent=AgentTarget(platform="custom", transport=TransportKind.TEXT),
        models=ModelSlots(simulator="stub", judge="stub"),
        personas=[
            Persona(
                id="priya",
                name="Priya",
                identity="A customer",
                goal="Cancel the plan",
            )
        ],
        scenarios=[
            Scenario(
                id="cancel",
                name="Cancel the plan",
                persona_id="priya",
                max_turns=2,
                success_criteria="Cancellation is acknowledged",
                expected_tools=["cancel_subscription"],
            )
        ],
    )


@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Caller turns and the judge verdict both route through acomplete()."""

    async def caller(**kwargs: Any) -> str:
        _ = kwargs
        return "I'd like to cancel my plan, please."

    async def judge(**kwargs: Any) -> str:
        _ = kwargs
        return json.dumps(
            {
                "score": 0.9,
                "reason": "Handled.",
                "suggestions": [],
            }
        )

    monkeypatch.setattr("wiretap.agent.orchestrator.acomplete", caller)
    monkeypatch.setattr("wiretap.eval.judge.acomplete", judge)


def test_unsupported_transport_reports_unobservable_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    suite = _suite()

    artifact = asyncio.run(
        simulate_scenario(suite, suite.scenarios[0], suite_id="t", cwd=tmp_path)
    )

    assert artifact.tool_calls == []
    assert artifact.meta["tool_capture"] == "unsupported"
    assert artifact.metrics["tool_calls"] == 0
    # The diff still records the gap, but capture status is what gates the judge.
    assert artifact.metrics["missing_tools"] == ["cancel_subscription"]
    assert artifact.metrics["unexpected_tools"] == []


def test_unobservable_capture_keeps_tools_out_of_the_judge_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The agent must not be blamed for tools we had no way to see."""
    monkeypatch.chdir(tmp_path)
    seen: list[str] = []

    async def judge(**kwargs: Any) -> str:
        seen.extend(m["content"] for m in kwargs["messages"])
        return json.dumps(
            {"score": 0.9, "reason": "Handled.", "suggestions": []}
        )

    monkeypatch.setattr("wiretap.eval.judge.acomplete", judge)
    suite = _suite()

    asyncio.run(simulate_scenario(suite, suite.scenarios[0], suite_id="t", cwd=tmp_path))

    prompt = "\n".join(seen)
    assert "cancel_subscription" not in prompt
    assert "The live agent's backend recorded" not in prompt
