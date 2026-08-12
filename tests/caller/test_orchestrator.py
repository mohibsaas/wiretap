"""Orchestrator / Pipecat Flows IR tests."""

from __future__ import annotations

from wiretap.caller.orchestrator import TestAgentOrchestrator, phases_to_nodes
from wiretap.models import Beat, Persona


def _persona() -> Persona:
    return Persona(
        id="p1",
        identity="frustrated customer",
        goal="cancel subscription",
        personality="direct",
    )


def test_phases_to_single_node() -> None:
    nodes = phases_to_nodes(
        persona=_persona(),
        success_criteria="cancelled",
        phases=None,
    )
    assert len(nodes) == 1
    assert nodes[0][0] == "main"
    assert "role_message" in nodes[0][1]


def test_phases_to_multi_node() -> None:
    nodes = phases_to_nodes(
        persona=_persona(),
        success_criteria="cancelled",
        phases=[
            {"id": "greet", "task": "say hello", "max_turns": 2},
            {"id": "cancel", "task": "request cancellation", "max_turns": 3},
        ],
    )
    assert [n[0] for n in nodes] == ["greet", "cancel"]
    assert "greet" in (nodes[0][1].get("task_messages") or [{}])[0].get("content", "")


def test_orchestrator_beat_and_describe(monkeypatch) -> None:
    monkeypatch.setattr(
        "wiretap.caller.orchestrator.complete",
        lambda **kwargs: "I want to cancel [[HANGUP]]",
    )
    orch = TestAgentOrchestrator(
        persona=_persona(),
        success_criteria="cancelled",
        model="gpt-4o-mini",
        phases=[{"id": "a", "task": "cancel", "max_turns": 2}],
        beats=[Beat(at_turn=1, say="Please cancel now")],
        speech=None,
    )
    text, hangup = orch.next_utterance()
    assert text == "Please cancel now"
    assert hangup is False
    desc = orch.describe()
    assert desc["orchestrator"] == "pipecat.flows"
    assert desc["current_node"] == "a"
    assert len(desc["nodes"]) == 1


def test_orchestrator_llm_hangup(monkeypatch) -> None:
    monkeypatch.setattr(
        "wiretap.caller.orchestrator.complete",
        lambda **kwargs: "Done [[HANGUP]]",
    )
    orch = TestAgentOrchestrator(
        persona=_persona(),
        success_criteria="cancelled",
        model="gpt-4o-mini",
        speech=None,
    )
    orch.observe_agent("How can I help?")
    text, hangup = orch.next_utterance()
    assert "Done" in text
    assert hangup is True
