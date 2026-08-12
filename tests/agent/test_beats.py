"""Agent package tests."""

from wiretap.agent import beat_for_turn
from wiretap.models import Beat


def test_beat_at_turn() -> None:
    beats = [Beat(at_turn=1, say="cancel"), Beat(after_turns=4, must_include="refund")]
    assert beat_for_turn(beats, 1) is not None
    assert beat_for_turn(beats, 1).say == "cancel"
    assert beat_for_turn(beats, 4).must_include == "refund"
    assert beat_for_turn(beats, 2) is None
