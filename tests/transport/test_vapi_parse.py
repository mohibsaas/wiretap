"""Vapi chat output parsing."""

from wiretap.transport.vapi import _extract_vapi_output


def test_extract_string_output() -> None:
    assert _extract_vapi_output({"output": [{"content": "Hello there"}]}) == "Hello there"


def test_extract_nested_text() -> None:
    data = {
        "output": [
            {"content": [{"type": "text", "text": "Part A"}, {"type": "text", "text": "Part B"}]}
        ]
    }
    assert "Part A" in _extract_vapi_output(data)
