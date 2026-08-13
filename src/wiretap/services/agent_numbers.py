"""Find the phone number that reaches a live agent, and remember the choice.

Dialing an agent over PSTN needs the number the platform routes to it. That
mapping already exists on the platform, so it is read back rather than typed:
Retell and Vapi both expose the numbers bound to an agent. Platforms without
such an API return nothing and the caller falls back to manual entry.

Discovery is advisory — a network failure must never block a run — so nothing
here raises. The pick is cached per agent so later runs are one keypress.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from wiretap.paths import wiretap_root
from wiretap.services.twilio_pstn import normalize_e164

RETELL_API = "https://api.retellai.com"
VAPI_API = "https://api.vapi.ai"

DISCOVERY_TIMEOUT_SECONDS = 20.0
SETTINGS_FILENAME = "phone.json"

# Platforms whose API can name the numbers bound to an agent.
DISCOVERABLE_PLATFORMS = ("retell", "vapi")


@dataclass(frozen=True)
class AgentNumber:
    """A dialable number on the platform account."""

    number: str
    label: str
    bound: bool  # routed to the agent under test


async def discover_agent_numbers(
    *,
    platform: str | None,
    agent_id: str | None,
    api_key: str,
    client: httpx.AsyncClient | None = None,
) -> list[AgentNumber]:
    """Numbers on the platform account, the agent's own ones first.

    Empty when the platform has no number API, the credentials are missing, or
    the call fails — every one of those means "ask the user instead".
    """
    name = (platform or "").lower().strip()
    reader = {"retell": _read_retell, "vapi": _read_vapi}.get(name)
    if reader is None or not api_key:
        return []

    try:
        if client is not None:
            found = await reader(client, agent_id, api_key)
        else:
            async with httpx.AsyncClient(timeout=DISCOVERY_TIMEOUT_SECONDS) as owned:
                found = await reader(owned, agent_id, api_key)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return []
    return sorted(found, key=lambda n: (not n.bound, n.number))


async def _read_retell(
    client: httpx.AsyncClient, agent_id: str | None, api_key: str
) -> list[AgentNumber]:
    resp = await client.get(
        f"{RETELL_API}/list-phone-numbers",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    resp.raise_for_status()
    records = resp.json()
    if not isinstance(records, list):
        return []

    numbers = []
    for record in records:
        if not isinstance(record, dict):
            continue
        number = _dialable(record.get("phone_number"))
        if not number:
            continue
        label = str(
            record.get("nickname") or record.get("phone_number_pretty") or ""
        ).strip()
        numbers.append(
            AgentNumber(
                number=number,
                label=label,
                bound=bool(agent_id) and agent_id in _retell_agent_ids(record),
            )
        )
    return numbers


def _retell_agent_ids(record: dict[str, Any]) -> set[str]:
    """Agents bound to a number, across both the weighted and legacy shapes.

    Retell replaced the single ``inbound_agent_id`` field with weighted agent
    lists in March 2026; records written before that still carry the old field.
    """
    ids: set[str] = set()
    for key in ("inbound_agents", "outbound_agents"):
        entries = record.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and entry.get("agent_id"):
                ids.add(str(entry["agent_id"]))
    for key in ("inbound_agent_id", "outbound_agent_id"):
        value = record.get(key)
        if value:
            ids.add(str(value))
    return ids


async def _read_vapi(
    client: httpx.AsyncClient, agent_id: str | None, api_key: str
) -> list[AgentNumber]:
    resp = await client.get(
        f"{VAPI_API}/phone-number",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    resp.raise_for_status()
    records = resp.json()
    if not isinstance(records, list):
        return []

    numbers = []
    for record in records:
        if not isinstance(record, dict):
            continue
        number = _dialable(record.get("number"))
        if not number:
            continue
        numbers.append(
            AgentNumber(
                number=number,
                label=str(record.get("name") or "").strip(),
                bound=bool(agent_id) and str(record.get("assistantId") or "") == agent_id,
            )
        )
    return numbers


def _dialable(value: Any) -> str | None:
    """Drop anything we could not place a call to, such as a BYO SIP URI."""
    try:
        return normalize_e164(str(value or ""))
    except ValueError:
        return None


def settings_path(cwd: Path | None = None) -> Path:
    return wiretap_root(cwd) / SETTINGS_FILENAME


def cache_key(platform: str | None, agent_id: str | None) -> str:
    return f"{(platform or 'custom').lower().strip()}:{agent_id or '-'}"


def saved_agent_number(
    *,
    platform: str | None,
    agent_id: str | None,
    cwd: Path | None = None,
) -> str | None:
    """The number picked for this agent on a previous run."""
    path = settings_path(cwd)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    targets = (data or {}).get("targets")
    if not isinstance(targets, dict):
        return None
    number = str(targets.get(cache_key(platform, agent_id)) or "").strip()
    return number or None


def save_agent_number(
    number: str,
    *,
    platform: str | None,
    agent_id: str | None,
    cwd: Path | None = None,
) -> str:
    """Persist the pick so later runs default to it."""
    number = normalize_e164(number, field="agent phone number")
    path = settings_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError):
            data = {}
    targets = data.get("targets")
    if not isinstance(targets, dict):
        targets = {}
    targets[cache_key(platform, agent_id)] = number
    data["targets"] = targets
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return number


__all__ = [
    "DISCOVERABLE_PLATFORMS",
    "RETELL_API",
    "VAPI_API",
    "AgentNumber",
    "cache_key",
    "discover_agent_numbers",
    "save_agent_number",
    "saved_agent_number",
    "settings_path",
]
