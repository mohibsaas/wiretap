"""Retell transport — shared audio turn gate (provider-agnostic)."""

from __future__ import annotations

from wiretap.transport.retell import RetellTransport
from wiretap.transport.turn_gate import AgentTurnGate, receive_coalesced, speak_with_gate_mute


def test_retell_uses_shared_turn_gate_helpers() -> None:
    """Retell must not own a parallel turn-detection path."""
    assert not hasattr(RetellTransport, "_handle_data")
    assert not hasattr(RetellTransport, "_handle_timing_hint")
    assert not hasattr(RetellTransport, "_agent_talking")
    assert not hasattr(RetellTransport, "_commit_draft")
    # Shared helpers exist for all live audio transports.
    assert callable(receive_coalesced)
    assert callable(speak_with_gate_mute)
    assert AgentTurnGate is not None


def test_retell_configure_speech_sets_stt() -> None:
    t = RetellTransport()
    t.configure_speech(stt="deepgram", tts="pyai", voice="alloy")
    assert t._stt_name == "deepgram"
    assert t._tts_name == "pyai"
