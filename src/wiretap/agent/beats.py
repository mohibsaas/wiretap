"""Beat selection for the caller."""

from __future__ import annotations

from wiretap.models import Beat


def beat_for_turn(beats: list[Beat], turn: int) -> Beat | None:
    """Return the beat for a 1-based caller turn, if any."""
    for beat in beats:
        if beat.at_turn is not None and beat.at_turn == turn:
            return beat
        if beat.after_turns is not None and turn == beat.after_turns:
            return beat
    return None
