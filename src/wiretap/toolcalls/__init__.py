"""Fetch the tool calls a live agent made, after the call ended.

Every platform documents these fields as available only once the call is over,
so this polls briefly before giving up. A capture status travels with the
records because an empty list and an unobservable call must never look alike —
the judge would otherwise blame the agent for tools we simply could not see.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from wiretap.models import AgentTarget, ToolCallRecord
from wiretap.toolcalls import elevenlabs, retell, vapi
from wiretap.transport.base import CallRef

CAPTURE_OK = "ok"
CAPTURE_UNSUPPORTED = "unsupported"
CAPTURE_ERROR = "error"

FETCH_ATTEMPTS = 3
FETCH_DELAY_SECONDS = 2.0
FETCH_TIMEOUT_SECONDS = 20.0


# Each module exposes fetch_call() / is_ready() / normalize() / DEFAULT_TOKEN_ENV.
_FETCHERS: dict[str, Any] = {
    "retell": retell,
    "vapi": vapi,
    "elevenlabs": elevenlabs,
}

# A record that is not there yet looks exactly like a transport failure, so
# every attempt is retried rather than aborting the whole fetch.
_TRANSIENT = (httpx.HTTPError, ValueError, KeyError, TypeError)

# Retrying these only delays the run: a key that cannot read calls now still
# cannot read them in two seconds.
_PERMANENT_STATUS = frozenset({401, 403})


async def collect_tool_calls(
    ref: CallRef | None,
    target: AgentTarget,
    *,
    attempts: int = FETCH_ATTEMPTS,
    delay: float = FETCH_DELAY_SECONDS,
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> tuple[list[ToolCallRecord], str]:
    """Records plus a capture status. Never raises — a run must not fail here."""
    if ref is None:
        return [], CAPTURE_UNSUPPORTED
    module = _FETCHERS.get(ref.platform)
    if module is None or not ref.call_id:
        return [], CAPTURE_UNSUPPORTED

    try:
        from wiretap.providers.env import require_env

        key = require_env(target.token_env or module.DEFAULT_TOKEN_ENV)
    except (RuntimeError, ValueError):
        return [], CAPTURE_ERROR

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
            for attempt in range(max(1, attempts)):
                try:
                    payload = await module.fetch_call(client, ref.call_id, key)
                    if module.is_ready(payload):
                        return module.normalize(payload), CAPTURE_OK
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in _PERMANENT_STATUS:
                        return [], CAPTURE_ERROR
                except _TRANSIENT:
                    pass
                if attempt < attempts - 1:
                    await sleep(delay)
    except _TRANSIENT:
        return [], CAPTURE_ERROR
    return [], CAPTURE_ERROR


def tool_diff(
    expected: list[str], actual: list[ToolCallRecord]
) -> tuple[list[str], list[str]]:
    """(missing, unexpected) by name — informational, never flips pass/fail."""
    called = {r.name for r in actual if r.name}
    wanted = [t for t in dict.fromkeys(expected) if t]
    missing = [t for t in wanted if t not in called]
    unexpected = [n for n in dict.fromkeys(r.name for r in actual if r.name) if n not in wanted]
    return missing, unexpected


__all__ = [
    "CAPTURE_ERROR",
    "CAPTURE_OK",
    "CAPTURE_UNSUPPORTED",
    "collect_tool_calls",
    "tool_diff",
]
