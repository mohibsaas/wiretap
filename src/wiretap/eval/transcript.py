"""Format transcripts for judge / rules."""

from __future__ import annotations

from wiretap.models import TurnRecord


def transcript_text(turns: list[TurnRecord]) -> str:
    lines = []
    for t in turns:
        who = "Caller" if t.role == "user" else "Agent"
        lines.append(f"{who}: {t.text}")
    return "\n".join(lines)
