"""Helpers to commit complete agent utterances (not streaming prefixes)."""

from __future__ import annotations


def normalize_agent_text(text: str | None) -> str:
    return (text or "").strip()


def accept_final_utterance(text: str, seen: set[str]) -> str | None:
    """Return text to enqueue once, preferring longer finals over prefixes.

    Returns None if ``text`` is empty, already seen, or a shorter prefix of a
    previously accepted utterance.
    """
    text = normalize_agent_text(text)
    if not text or text in seen:
        return None
    # Drop shorter prefixes so a later longer final can be accepted.
    shorter = {s for s in seen if text.startswith(s) and text != s}
    seen -= shorter
    if any(prev.startswith(text) and prev != text for prev in seen):
        return None
    seen.add(text)
    return text


def is_vapi_final_transcript(data: dict) -> bool:
    """Vapi sends partial + final assistant transcripts; only finals are turns."""
    t = str(data.get("transcriptType") or data.get("transcript_type") or "final").lower()
    return t in {"final", "end", ""}
