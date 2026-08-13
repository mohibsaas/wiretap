"""ElevenLabs tool calls — GET /v1/convai/conversations/{id}.

Tool calls nest inside the transcript turn that triggered them, so both the
turn index and a turn-granularity timestamp come for free.
"""

from __future__ import annotations

from typing import Any

import httpx

from wiretap.models import ToolCallRecord
from wiretap.toolcalls.common import build_record, cap_records, status_from_flag

ELEVEN_API = "https://api.elevenlabs.io"
DEFAULT_TOKEN_ENV = "ELEVENLABS_API_KEY"


async def fetch_call(client: httpx.AsyncClient, call_id: str, key: str) -> dict[str, Any]:
    resp = await client.get(
        f"{ELEVEN_API}/v1/convai/conversations/{call_id}",
        headers={"xi-api-key": key},
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def is_ready(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    if status in {"done", "completed", "failed"}:
        return True
    # "processing" means the transcript is still being assembled.
    return status not in {"processing", "initiated", "in-progress"} and bool(
        payload.get("transcript")
    )


def _seconds(turn: dict[str, Any]) -> float | None:
    value = turn.get("time_in_call_secs")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize(payload: dict[str, Any]) -> list[ToolCallRecord]:
    """Pair tool_calls with tool_results on request_id, within each turn."""
    transcript = payload.get("transcript")
    if not isinstance(transcript, list):
        return []

    out: list[ToolCallRecord] = []
    for turn_index, turn in enumerate(transcript):
        if not isinstance(turn, dict):
            continue
        calls = turn.get("tool_calls")
        if not isinstance(calls, list) or not calls:
            continue

        results: dict[str, dict[str, Any]] = {}
        raw_results = turn.get("tool_results")
        if isinstance(raw_results, list):
            for result in raw_results:
                if isinstance(result, dict):
                    request_id = str(result.get("request_id") or "")
                    if request_id:
                        results[request_id] = result

        at_seconds = _seconds(turn)
        for call in calls:
            if not isinstance(call, dict):
                continue
            result = results.get(str(call.get("request_id") or "")) or {}
            is_error = result.get("is_error")
            out.append(
                build_record(
                    name=str(call.get("tool_name") or ""),
                    arguments=call.get("params_as_json"),
                    result=result.get("result_value"),
                    # is_error inverts: True means the tool failed.
                    status=status_from_flag(
                        None if is_error is None else not bool(is_error)
                    ),
                    turn_index=turn_index,
                    at_seconds=at_seconds,
                )
            )
    return cap_records(out)


__all__ = ["DEFAULT_TOKEN_ENV", "ELEVEN_API", "fetch_call", "is_ready", "normalize"]
