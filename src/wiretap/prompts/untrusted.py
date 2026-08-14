"""Neutralize markup in text the system under test authored.

Transcripts, imported agent prompts and tool arguments all reach our prompts as
data. Raw ``<`` would let that content close a section and address the model
directly, so it never survives into a prompt as markup.
"""

from __future__ import annotations

_ANGLE_BRACKETS = str.maketrans({"<": "&lt;", ">": "&gt;"})


def quote_untrusted(text: str) -> str:
    """Escape angle brackets so call content cannot forge prompt sections."""
    return (text or "").translate(_ANGLE_BRACKETS)


__all__ = ["quote_untrusted"]
