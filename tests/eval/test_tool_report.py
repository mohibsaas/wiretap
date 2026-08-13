"""Rendering tool evidence for the judge."""

from wiretap.eval.tools import tool_report_text
from wiretap.models import ToolCallRecord

CALLS = [
    ToolCallRecord(
        name="extract_update_dynamic_variable",
        arguments={"ZipCode": "80301", "CallbackNumber": "[REDACTED]"},
        status="ok",
    ),
    ToolCallRecord(
        name="transfer_call",
        arguments={"reason": "caller asked for a manager"},
        result_summary="no agent available",
        status="error",
    ),
]


def test_report_lists_expected_actual_and_gaps() -> None:
    text = tool_report_text(
        expected=["extract_update_dynamic_variable", "check_current_date"],
        actual=CALLS,
        capture="ok",
    )
    assert "Expected for this scenario: extract_update_dynamic_variable" in text
    assert '1. extract_update_dynamic_variable(ZipCode="80301"' in text
    assert 'transfer_call(reason="caller asked for a manager") -> error' in text
    assert "Never called: check_current_date" in text
    assert "Called but not expected: transfer_call" in text


def test_report_empty_unless_capture_succeeded() -> None:
    for capture in ("unsupported", "error", ""):
        assert tool_report_text(expected=["a"], actual=CALLS, capture=capture) == ""


def test_report_empty_when_nothing_to_say() -> None:
    assert tool_report_text(expected=[], actual=[], capture="ok") == ""


def test_report_flags_expected_tool_that_never_fired() -> None:
    text = tool_report_text(expected=["book_appointment"], actual=[], capture="ok")
    assert "no tool calls recorded" in text
    assert "Never called: book_appointment" in text
