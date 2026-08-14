"""Stable fake caller contact facts for voice evals.

Personas often ship with empty ``knowledge``, so the simulator invents
unspeakable ZIP/phone strings. Fill missing contact fields with deterministic
fake defaults (not real PII) and format them for digit-by-digit TTS.
"""

from __future__ import annotations

from typing import Any

# Safe synthetic defaults — clearly fake, stable across runs.
DEFAULT_CONTACT_KNOWLEDGE: dict[str, str] = {
    "full_name": "Alex Rivera",
    "callback_phone": "5551234567",
    "zip_code": "90210",
}

_DIGIT_WORDS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}

_SPEAK_DIGIT_KEYS = (
    "zip",
    "postal",
    "phone",
    "callback",
    "mobile",
    "ssn",
    "account",
)


def speakable_digits(value: str) -> str:
    """Turn ``90210`` / ``555-123-4567`` into ``nine zero two one zero``."""
    chars: list[str] = []
    for ch in str(value):
        if ch.isdigit():
            chars.append(_DIGIT_WORDS[ch])
        elif ch.isalpha():
            chars.append(ch.upper())
    return " ".join(chars)


def enrich_persona_knowledge(knowledge: dict[str, Any] | None) -> dict[str, Any]:
    """Copy knowledge and fill missing contact fields with fake defaults."""
    out: dict[str, Any] = {
        str(k): v
        for k, v in (knowledge or {}).items()
        if v is not None and str(v).strip()
    }
    for key, value in DEFAULT_CONTACT_KNOWLEDGE.items():
        if key not in out:
            # Also skip if a close alias already exists (e.g. postal_code).
            aliases = {
                "zip_code": ("zip", "postal_code", "zipcode"),
                "callback_phone": ("phone", "phone_number", "mobile", "callback"),
                "full_name": ("name", "first_name", "caller_name"),
            }
            if any(a in out for a in aliases.get(key, ())):
                continue
            out[key] = value
    return out


def format_knowledge_for_prompt(knowledge: dict[str, Any] | None) -> str:
    """XML <knowledge> block with digit-speaking hints for codes/phones."""
    data = enrich_persona_knowledge(knowledge)
    if not data:
        return ""
    lines: list[str] = []
    for key, raw in data.items():
        value = str(raw).strip()
        lower = key.lower()
        if any(tok in lower for tok in _SPEAK_DIGIT_KEYS) and any(
            ch.isdigit() for ch in value
        ):
            spoken = speakable_digits(value)
            lines.append(f"- {key}: {value} (say digit-by-digit: \"{spoken}\")")
        else:
            lines.append(f"- {key}: {value}")
    body = "\n".join(lines)
    return f"""\
<knowledge>
{body}
</knowledge>

"""


__all__ = [
    "DEFAULT_CONTACT_KNOWLEDGE",
    "enrich_persona_knowledge",
    "format_knowledge_for_prompt",
    "speakable_digits",
]
