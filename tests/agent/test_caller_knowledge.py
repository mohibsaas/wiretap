"""Caller contact knowledge helpers for speakable ZIP/phone."""

from __future__ import annotations

from wiretap.prompts.caller_knowledge import (
    enrich_persona_knowledge,
    format_knowledge_for_prompt,
    speakable_digits,
)
from wiretap.prompts.test_agent import caller_role_message


def test_speakable_digits_zip() -> None:
    assert speakable_digits("90210") == "nine zero two one zero"
    assert speakable_digits("555-123-4567") == (
        "five five five one two three four five six seven"
    )


def test_enrich_fills_missing_contact_fields() -> None:
    out = enrich_persona_knowledge({})
    assert out["zip_code"] == "90210"
    assert out["callback_phone"] == "5551234567"
    assert out["full_name"] == "Alex Rivera"


def test_enrich_preserves_existing_zip() -> None:
    out = enrich_persona_knowledge({"zip_code": "10001", "full_name": "Sam"})
    assert out["zip_code"] == "10001"
    assert out["full_name"] == "Sam"
    assert out["callback_phone"] == "5551234567"


def test_format_knowledge_includes_digit_hint() -> None:
    block = format_knowledge_for_prompt({"zip_code": "90210"})
    assert "nine zero two one zero" in block
    assert "zip_code: 90210" in block


def test_caller_role_includes_zip_speech_rules_and_knowledge() -> None:
    role = caller_role_message(
        identity="A nervous caller",
        goal="Start intake",
        personality="calm",
        success_criteria="Agent collects zip",
        knowledge={},
    )
    assert "digit-by-digit" in role
    assert "nine zero two one zero" in role
    assert "alpha digit" in role  # banned example in rules
    assert "<knowledge>" in role
