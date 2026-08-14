"""Render recorded tool calls for the judge prompt.

Returns an empty string unless capture actually succeeded. That is the point:
showing a tool section for a call we could not observe invites the judge to
fail the agent for our blind spot rather than its behavior.
"""

from __future__ import annotations

from wiretap.models import ToolCallRecord

CAPTURE_OK = "ok"


def _arguments(record: ToolCallRecord) -> str:
    if not record.arguments:
        return ""
    parts = [f'{k}="{v}"' for k, v in record.arguments.items()]
    return ", ".join(parts)


def _outcome(record: ToolCallRecord) -> str:
    if record.status == "error":
        detail = record.result_summary.strip()
        return f'error: "{detail}"' if detail else "error"
    return record.status or "unknown"


def tool_report_text(
    *,
    expected: list[str],
    actual: list[ToolCallRecord],
    capture: str,
) -> str:
    if capture != CAPTURE_OK:
        return ""
    wanted = [t for t in dict.fromkeys(expected) if t.strip()]
    if not wanted and not actual:
        return ""

    lines: list[str] = []
    lines.append(
        "Expected for this scenario: " + (", ".join(wanted) if wanted else "(none)")
    )
    lines.append("")
    if actual:
        lines.append("Called, in order:")
        for i, record in enumerate(actual, start=1):
            args = _arguments(record)
            lines.append(f"{i}. {record.name}({args}) -> {_outcome(record)}")
    else:
        lines.append("Called, in order: (no tool calls recorded)")

    called = {r.name for r in actual if r.name}
    missing = [t for t in wanted if t not in called]
    unexpected = [n for n in dict.fromkeys(r.name for r in actual if r.name) if n not in wanted]
    if missing:
        lines.append("")
        lines.append("Never called: " + ", ".join(missing))
    if unexpected and wanted:
        lines.append("Called but not expected: " + ", ".join(unexpected))
    return "\n".join(lines)


__all__ = ["CAPTURE_OK", "tool_report_text"]
