"""Retell tool calls — GET /v2/get-call.

Retell weaves tool invocations and results into the transcript in conversation
order, so position is the only timing signal available (tool entries carry no
timestamp, unlike utterances whose words carry start/end).
"""

from __future__ import annotations

from typing import Any

import httpx

from wiretap.models import ToolCallRecord
from wiretap.toolcalls.common import build_record, cap_records, status_from_flag

RETELL_API = "https://api.retellai.com"
DEFAULT_TOKEN_ENV = "RETELL_API_KEY"


async def fetch_call(client: httpx.AsyncClient, call_id: str, key: str) -> dict[str, Any]:
    resp = await client.get(
        f"{RETELL_API}/v2/get-call/{call_id}",
        headers={"Authorization": f"Bearer {key}"},
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def is_ready(payload: dict[str, Any]) -> bool:
    """Tool calls are only populated once the call has ended."""
    status = str(payload.get("call_status") or "").strip().lower()
    if status in {"ended", "error"}:
        return True
    return bool(
        payload.get("transcript_with_tool_calls")
        or payload.get("scrubbed_transcript_with_tool_calls")
    )


def normalize(payload: dict[str, Any]) -> list[ToolCallRecord]:
    """Pair invocations with results on tool_call_id, keeping transcript order.

    Prefers the scrubbed transcript — Retell has already stripped PII from it,
    which beats our own best-effort redaction.
    """
    entries = payload.get("scrubbed_transcript_with_tool_calls")
    if not isinstance(entries, list) or not entries:
        entries = payload.get("transcript_with_tool_calls")
    if not isinstance(entries, list):
        return []

    results: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if isinstance(entry, dict) and entry.get("role") == "tool_call_result":
            call_id = str(entry.get("tool_call_id") or "")
            if call_id:
                results[call_id] = entry

    out: list[ToolCallRecord] = []
    turn_index = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        if role in {"agent", "user"}:
            turn_index += 1
            continue
        if role != "tool_call_invocation":
            continue
        result = results.get(str(entry.get("tool_call_id") or "")) or {}
        out.append(
            build_record(
                name=str(entry.get("name") or ""),
                arguments=entry.get("arguments"),
                result=result.get("content"),
                status=status_from_flag(result.get("successful")),
                turn_index=turn_index,
            )
        )
    return cap_records(out)


__all__ = ["DEFAULT_TOKEN_ENV", "RETELL_API", "fetch_call", "is_ready", "normalize"]
