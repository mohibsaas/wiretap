"""Caller contract meta-eval."""

from __future__ import annotations

from wiretap.eval.meta import check_caller_contract
from wiretap.models import Persona, TurnRecord


def test_no_live_speech_is_harness_fault() -> None:
    persona = Persona(id="p", identity="x", goal="y")
    v = check_caller_contract(persona=persona, turns=[])
    assert v and "never heard agent speech" in v[0]


def test_agent_only_is_caller_silence() -> None:
    persona = Persona(id="p", identity="x", goal="y")
    turns = [TurnRecord(role="agent", text="Hello?")]
    v = check_caller_contract(persona=persona, turns=turns)
    assert v == ["caller produced no utterances"]


def test_ok_with_user_turn() -> None:
    persona = Persona(id="p", identity="x", goal="y")
    turns = [
        TurnRecord(role="agent", text="Hi"),
        TurnRecord(role="user", text="Hello there"),
    ]
    assert check_caller_contract(persona=persona, turns=turns) == []
