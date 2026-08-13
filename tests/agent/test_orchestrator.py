"""Test-agent orchestrator tests."""

from __future__ import annotations

import asyncio

from wiretap.agent.orchestrator import TestAgentOrchestrator, phases_to_nodes
from wiretap.models import Beat, Persona


def _persona() -> Persona:
    return Persona(
        id="p1",
        identity="frustrated customer",
        goal="cancel subscription",
        personality="direct",
        constraints=["Do not reveal you are a test bot"],
        knowledge={"email": "caller@example.com"},
    )


def test_phases_to_single_node() -> None:
    nodes = phases_to_nodes(
        persona=_persona(),
        success_criteria="cancelled",
        phases=None,
    )
    assert len(nodes) == 1
    assert nodes[0].id == "main"
    assert nodes[0].role_message
    assert "Do not reveal you are a test bot" in nodes[0].role_message
    assert "caller@example.com" in nodes[0].role_message
    assert "<safety>" in nodes[0].role_message


def test_phases_to_multi_node() -> None:
    nodes = phases_to_nodes(
        persona=_persona(),
        success_criteria="cancelled",
        phases=[
            {"id": "greet", "task": "say hello", "max_turns": 2},
            {"id": "cancel", "task": "request cancellation", "max_turns": 3},
        ],
    )
    assert [n.id for n in nodes] == ["greet", "cancel"]
    assert "greet" in nodes[0].task_messages[0]["content"]


def test_orchestrator_beat_and_describe(monkeypatch) -> None:
    async def _fake(**kwargs: object) -> str:
        return "I want to cancel [[HANGUP]]"

    monkeypatch.setattr("wiretap.agent.orchestrator.acomplete", _fake)
    orch = TestAgentOrchestrator(
        persona=_persona(),
        success_criteria="cancelled",
        model="gpt-4o-mini",
        phases=[{"id": "a", "task": "cancel", "max_turns": 2}],
        beats=[Beat(at_turn=1, say="Please cancel now")],
        speech=None,
    )
    text, hangup = asyncio.run(orch.next_utterance())
    assert text == "Please cancel now"
    assert hangup is False
    desc = orch.describe()
    assert desc["orchestrator"] == "test_agent"
    assert desc["current_node"] == "a"
    assert len(desc["nodes"]) == 1


def test_orchestrator_llm_hangup(monkeypatch) -> None:
    async def _fake(**kwargs: object) -> str:
        return "Done [[HANGUP]]"

    monkeypatch.setattr("wiretap.agent.orchestrator.acomplete", _fake)
    orch = TestAgentOrchestrator(
        persona=_persona(),
        success_criteria="cancelled",
        model="gpt-4o-mini",
        speech=None,
    )
    orch.observe_agent("How can I help?")
    text, hangup = asyncio.run(orch.next_utterance())
    assert "Done" in text
    assert hangup is True


def test_concurrent_utterances_overlap(monkeypatch) -> None:
    """Regression: sync LiteLLM used to block the loop and serialize dials."""
    in_flight = 0
    max_in_flight = 0

    async def _slow(**kwargs: object) -> str:
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return "hello [[HANGUP]]"

    monkeypatch.setattr("wiretap.agent.orchestrator.acomplete", _slow)

    async def _run() -> None:
        a = TestAgentOrchestrator(
            persona=_persona(),
            success_criteria="cancelled",
            model="gpt-4o-mini",
            speech=None,
        )
        b = TestAgentOrchestrator(
            persona=_persona(),
            success_criteria="cancelled",
            model="gpt-4o-mini",
            speech=None,
        )
        await asyncio.gather(a.next_utterance(), b.next_utterance())

    asyncio.run(_run())
    assert max_in_flight == 2
