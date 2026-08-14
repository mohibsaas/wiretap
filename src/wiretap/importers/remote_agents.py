"""List remote voice agents from live platforms (for init dropdowns).

Uses the platform API key from the environment. Never logs or returns secrets.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from wiretap.providers.catalog import env_for_provider

_TIMEOUT = 8.0
_MAX = 50


def _key(env_name: str, *, cwd: Path | None, api_key: str | None) -> str | None:
    if api_key and api_key.strip():
        return api_key.strip()
    from wiretap.services.secrets import load_dotenv

    load_dotenv(cwd)
    return (os.environ.get(env_name) or "").strip() or None


def _norm(agents: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in agents:
        aid = str(item.get("id") or "").strip()
        name = str(item.get("name") or aid).strip() or aid
        if not aid or aid in seen:
            continue
        seen.add(aid)
        label = name if name == aid else f"{name}  ·  {aid}"
        out.append({"id": aid, "name": name, "label": label})
        if len(out) >= _MAX:
            break
    return out


def _fetch_retell(api_key: str) -> list[dict[str, str]]:
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(
            "https://api.retellai.com/v2/list-agents",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            params={"limit": _MAX},
            json={
                "filter_criteria": {
                    "channel": {"type": "string", "op": "eq", "value": "voice"}
                }
            },
        )
        # Older accounts / keys may still work without filter body.
        if resp.status_code >= 400:
            resp = client.post(
                "https://api.retellai.com/v2/list-agents",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                params={"limit": _MAX},
                json={},
            )
        resp.raise_for_status()
        data = resp.json()
    raw = data.get("items") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raw = data if isinstance(data, list) else []
    agents: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        aid = str(item.get("agent_id") or item.get("id") or "").strip()
        name = str(item.get("agent_name") or item.get("name") or aid).strip()
        if aid:
            agents.append({"id": aid, "name": name})
    return _norm(agents)


def _fetch_vapi(api_key: str) -> list[dict[str, str]]:
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(
            "https://api.vapi.ai/assistant",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"limit": _MAX},
        )
        resp.raise_for_status()
        data = resp.json()
    raw = data if isinstance(data, list) else (data.get("data") or data.get("results") or [])
    agents: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            aid = str(item.get("id") or "").strip()
            name = str(item.get("name") or aid).strip()
            if aid:
                agents.append({"id": aid, "name": name})
    return _norm(agents)


def _fetch_elevenlabs(api_key: str) -> list[dict[str, str]]:
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(
            "https://api.elevenlabs.io/v1/convai/agents",
            headers={"xi-api-key": api_key, "Accept": "application/json"},
            params={"page_size": _MAX},
        )
        resp.raise_for_status()
        data = resp.json() or {}
    raw = data.get("agents") or data.get("data") or []
    agents: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            aid = str(item.get("agent_id") or item.get("id") or "").strip()
            name = str(item.get("name") or aid).strip()
            if aid:
                agents.append({"id": aid, "name": name})
    return _norm(agents)


_FETCHERS = {
    "retell": ("RETELL_API_KEY", _fetch_retell),
    "vapi": ("VAPI_API_KEY", _fetch_vapi),
    "elevenlabs": ("ELEVENLABS_API_KEY", _fetch_elevenlabs),
}


def list_remote_agents(
    platform: str,
    *,
    api_key: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """List agents for a platform. ``source`` is ``live`` or ``unavailable``."""
    pid = (platform or "").lower().strip()
    if pid not in _FETCHERS:
        return {
            "platform": pid,
            "agents": [],
            "source": "unavailable",
            "live_supported": False,
            "error": "not_supported",
        }
    env_name, fetcher = _FETCHERS[pid]
    key = _key(env_name, cwd=cwd, api_key=api_key)
    if not key:
        # Also try catalog alias if different
        key = _key(env_for_provider(pid), cwd=cwd, api_key=None)
    if not key:
        return {
            "platform": pid,
            "agents": [],
            "source": "unavailable",
            "live_supported": True,
            "error": "no_api_key",
        }
    try:
        agents = fetcher(key)
    except httpx.HTTPStatusError as exc:
        return {
            "platform": pid,
            "agents": [],
            "source": "unavailable",
            "live_supported": True,
            "error": f"http_{exc.response.status_code}",
        }
    except httpx.TimeoutException:
        return {
            "platform": pid,
            "agents": [],
            "source": "unavailable",
            "live_supported": True,
            "error": "timeout",
        }
    except Exception as exc:
        return {
            "platform": pid,
            "agents": [],
            "source": "unavailable",
            "live_supported": True,
            "error": type(exc).__name__,
        }
    if not agents:
        return {
            "platform": pid,
            "agents": [],
            "source": "unavailable",
            "live_supported": True,
            "error": "empty_response",
        }
    return {
        "platform": pid,
        "agents": agents,
        "source": "live",
        "live_supported": True,
        "error": None,
    }


__all__ = ["list_remote_agents"]
