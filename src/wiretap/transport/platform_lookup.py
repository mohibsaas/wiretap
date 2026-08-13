"""Find the platform's own id for a call we placed over PSTN.

Other transports create the call through the platform's API and get an id back.
A PSTN dial goes through the carrier instead, so the id has to be recovered
afterwards by matching the platform's most recent call for that agent against
the window we dialed in. A miss is normal and reported as unsupported capture,
never as a failure — so nothing here raises.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

RETELL_API = "https://api.retellai.com"
VAPI_API = "https://api.vapi.ai"

LOOKUP_TIMEOUT_SECONDS = 20.0
# Clock skew plus the seconds between our dial and the platform's record.
DIAL_WINDOW_SLACK = timedelta(seconds=90)
LOOKUP_LIMIT = 20


async def resolve_platform_call_id(
    *,
    platform: str,
    agent_id: str | None,
    api_key: str,
    dialed_at: datetime,
    phone_number: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """Best-effort platform call id, or None when it cannot be matched."""
    name = (platform or "").lower().strip()
    resolver = {"retell": _resolve_retell, "vapi": _resolve_vapi}.get(name)
    if resolver is None or not agent_id or not api_key:
        return None

    since = dialed_at.astimezone(UTC) - DIAL_WINDOW_SLACK
    try:
        if client is not None:
            return await resolver(client, agent_id, api_key, since, phone_number)
        async with httpx.AsyncClient(timeout=LOOKUP_TIMEOUT_SECONDS) as owned:
            return await resolver(owned, agent_id, api_key, since, phone_number)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


async def _resolve_retell(
    client: httpx.AsyncClient,
    agent_id: str,
    api_key: str,
    since: datetime,
    phone_number: str | None,
) -> str | None:
    resp = await client.post(
        f"{RETELL_API}/v2/list-calls",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "filter_criteria": {"agent_id": [agent_id]},
            "sort_order": "descending",
            "limit": LOOKUP_LIMIT,
        },
    )
    resp.raise_for_status()
    calls = resp.json()
    if not isinstance(calls, list):
        return None

    floor_ms = since.timestamp() * 1000
    fresh = [
        call
        for call in calls
        if isinstance(call, dict)
        and call.get("call_id")
        and _as_float(call.get("start_timestamp")) >= floor_ms
    ]
    if not fresh:
        return None
    matched = [c for c in fresh if _same_number(c.get("to_number"), phone_number)]
    best = max(matched or fresh, key=lambda c: _as_float(c.get("start_timestamp")))
    return str(best["call_id"])


async def _resolve_vapi(
    client: httpx.AsyncClient,
    agent_id: str,
    api_key: str,
    since: datetime,
    phone_number: str | None,
) -> str | None:
    resp = await client.get(
        f"{VAPI_API}/call",
        headers={"Authorization": f"Bearer {api_key}"},
        params={
            "assistantId": agent_id,
            "createdAtGt": since.isoformat().replace("+00:00", "Z"),
            "limit": LOOKUP_LIMIT,
        },
    )
    resp.raise_for_status()
    calls = resp.json()
    if not isinstance(calls, list):
        return None
    for call in calls:
        if isinstance(call, dict) and call.get("id"):
            return str(call["id"])
    return None


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _same_number(left: Any, right: Any) -> bool:
    if not left or not right:
        return False
    return str(left).strip() == str(right).strip()


__all__ = ["DIAL_WINDOW_SLACK", "RETELL_API", "VAPI_API", "resolve_platform_call_id"]
