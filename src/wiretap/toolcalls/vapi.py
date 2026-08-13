"""Vapi tool calls — GET /call/{id}.

Vapi is the only platform that timestamps tool activity: every message carries
secondsFromStart, so at_seconds is populated directly.
"""

from __future__ import annotations

from typing import Any

import httpx

from wiretap.models import ToolCallRecord
from wiretap.toolcalls.common import (
    build_record,
    cap_records,
    status_from_result,
    summarize_result,
)

VAPI_API = "https://api.vapi.ai"
DEFAULT_TOKEN_ENV = "VAPI_API_KEY"


async def fetch_call(client: httpx.AsyncClient, call_id: str, key: str) -> dict[str, Any]:
    resp = await client.get(
        f"{VAPI_API}/call/{call_id}",
        headers={"Authorization": f"Bearer {key}"},
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def is_ready(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    if status == "ended":
        return True
    return bool(_messages(payload))


def _messages(payload: dict[str, Any]) -> list[Any]:
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        artifact = payload.get("artifact")
        if isinstance(artifact, dict):
            messages = artifact.get("messages")
    return messages if isinstance(messages, list) else []


def _seconds(entry: dict[str, Any]) -> float | None:
    value = entry.get("secondsFromStart")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize(payload: dict[str, Any]) -> list[ToolCallRecord]:
    """Pair role=tool_calls entries with their tool_call_result on toolCallId."""
    messages = _messages(payload)

    results: dict[str, dict[str, Any]] = {}
    for entry in messages:
        if isinstance(entry, dict) and entry.get("role") == "tool_call_result":
            call_id = str(entry.get("toolCallId") or "")
            if call_id:
                results[call_id] = entry

    out: list[ToolCallRecord] = []
    turn_index = 0
    for entry in messages:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        if role in {"assistant", "bot", "user"}:
            turn_index += 1
            continue
        if role != "tool_calls":
            continue
        calls = entry.get("toolCalls")
        if not isinstance(calls, list):
            continue
        for call in calls:
            if not isinstance(call, dict):
                continue
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            result = results.get(str(call.get("id") or "")) or {}
            # Vapi reports no success flag — infer only from the result body.
            summary = summarize_result(result.get("result"))
            out.append(
                build_record(
                    name=str(fn.get("name") or call.get("name") or ""),
                    arguments=fn.get("arguments", call.get("arguments")),
                    result=result.get("result"),
                    status=status_from_result(summary),
                    turn_index=turn_index,
                    at_seconds=_seconds(entry),
                )
            )
    return cap_records(out)


__all__ = ["DEFAULT_TOKEN_ENV", "VAPI_API", "fetch_call", "is_ready", "normalize"]
