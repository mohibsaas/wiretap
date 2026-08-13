"""Shared normalization for platform tool-call payloads.

Everything here leaves the machine twice — it is written to the simulation
artifact and rendered into the judge prompt — so argument values and tool
results are scrubbed before a ``ToolCallRecord`` is ever built.
"""

from __future__ import annotations

import json
from typing import Any

from wiretap.models import ToolCallRecord
from wiretap.services.agent_brief import sanitize_text

ARG_VALUE_CAP = 160
RESULT_CAP = 240
MAX_TOOL_CALLS = 60

STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_UNKNOWN = "unknown"

# Result bodies platforms return when a tool never actually produced anything.
_FAILED_RESULT_HINTS = (
    "no result returned",
    "error",
    "failed",
    "timeout",
    "timed out",
    "exception",
    "unauthorized",
    "not found",
)


def parse_arguments(raw: Any) -> dict[str, Any]:
    """Coerce a platform's arguments blob into a flat, sanitized dict.

    Platforms send either a JSON string (Retell, Vapi, ElevenLabs) or an object.
    Non-object JSON still needs to reach the judge, so it is kept under
    ``value`` rather than dropped.
    """
    data: Any = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {"value": sanitize_text(text, cap=ARG_VALUE_CAP)}
    if isinstance(data, dict):
        return {
            str(k): _sanitize_value(v)
            for k, v in data.items()
            if str(k).strip()
        }
    if data is None:
        return {}
    return {"value": _sanitize_value(data)}


def _sanitize_value(value: Any) -> Any:
    """Scrub strings; stringify containers so nested PII cannot slip through."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        # Long digit runs (phone numbers, account ids) must still be scrubbed.
        return sanitize_text(str(value), cap=ARG_VALUE_CAP)
    if isinstance(value, str):
        return sanitize_text(value, cap=ARG_VALUE_CAP)
    return sanitize_text(json.dumps(value, ensure_ascii=False), cap=ARG_VALUE_CAP)


def summarize_result(raw: Any, *, cap: int = RESULT_CAP) -> str:
    if raw is None:
        return ""
    text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
    return sanitize_text(str(text), cap=cap)


def status_from_flag(flag: Any) -> str:
    """Map an explicit success/error flag. Absent means unstated, not failure."""
    if flag is None:
        return STATUS_UNKNOWN
    return STATUS_OK if bool(flag) else STATUS_ERROR


def status_from_result(result: str) -> str:
    """Best-effort status where the platform reports no explicit flag."""
    if not result.strip():
        return STATUS_UNKNOWN
    low = result.lower()
    if any(hint in low for hint in _FAILED_RESULT_HINTS):
        return STATUS_ERROR
    return STATUS_UNKNOWN


def build_record(
    *,
    name: str,
    arguments: Any = None,
    result: Any = None,
    status: str = STATUS_UNKNOWN,
    turn_index: int | None = None,
    at_seconds: float | None = None,
) -> ToolCallRecord:
    return ToolCallRecord(
        name=str(name or "").strip() or "(unnamed tool)",
        arguments=parse_arguments(arguments),
        result_summary=summarize_result(result),
        status=status,
        turn_index=turn_index,
        at_seconds=at_seconds,
    )


def cap_records(records: list[ToolCallRecord]) -> list[ToolCallRecord]:
    """Bound the payload — chatty agents can call tools on every single turn."""
    return records[:MAX_TOOL_CALLS]


__all__ = [
    "ARG_VALUE_CAP",
    "MAX_TOOL_CALLS",
    "RESULT_CAP",
    "STATUS_ERROR",
    "STATUS_OK",
    "STATUS_UNKNOWN",
    "build_record",
    "cap_records",
    "parse_arguments",
    "status_from_flag",
    "status_from_result",
    "summarize_result",
]
