"""Live TTS voice catalogs — fetch when an API key is available.

Curated shortlists in ``catalog.py`` remain the offline / failure fallback.
This module never logs or returns API keys.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from wiretap.providers.catalog import (
    default_voice_for,
    env_for_provider,
    voices_for_tts,
)

# Providers with a reliable list-voices HTTP API.
_LIVE_TTS = frozenset({"pyai", "elevenlabs", "cartesia"})
_TIMEOUT = 4.0
_MAX_VOICES = 80


def _normalize(voices: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in voices:
        vid = str(item.get("id") or "").strip()
        label = str(item.get("label") or vid).strip() or vid
        if not vid or vid in seen:
            continue
        seen.add(vid)
        out.append({"id": vid, "label": label})
        if len(out) >= _MAX_VOICES:
            break
    return out


def _fetch_pyai(api_key: str) -> list[dict[str, str]]:
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(
            "https://api.pyai.com/v1/voices",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
    raw = data if isinstance(data, list) else (data.get("data") or data.get("voices") or [])
    voices: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            vid = str(item.get("voice_id") or item.get("id") or "").strip()
            label = str(item.get("name") or item.get("label") or vid).strip()
            if vid:
                voices.append({"id": vid, "label": label})
    return _normalize(voices)


def _fetch_elevenlabs(api_key: str) -> list[dict[str, str]]:
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(
            "https://api.elevenlabs.io/v1/voices",
            params={"show_legacy": "true"},
            headers={"xi-api-key": api_key, "Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json() or {}
    raw = data.get("voices") or []
    voices: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            vid = str(item.get("voice_id") or "").strip()
            label = str(item.get("name") or vid).strip()
            if vid:
                voices.append({"id": vid, "label": label})
    return _normalize(voices)


def _fetch_cartesia(api_key: str) -> list[dict[str, str]]:
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(
            "https://api.cartesia.ai/voices",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Cartesia-Version": "2024-06-10",
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
    raw = data if isinstance(data, list) else (data.get("data") or data.get("voices") or [])
    voices: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            vid = str(item.get("id") or "").strip()
            label = str(item.get("name") or vid).strip()
            if vid:
                voices.append({"id": vid, "label": label})
    return _normalize(voices)


def fetch_tts_voices(
    provider: str, api_key: str
) -> tuple[list[dict[str, str]] | None, str | None]:
    """Hit the vendor list-voices API.

    Returns ``(voices, error)`` — ``error`` is a short reason with no secrets.
    """
    pid = (provider or "").lower().strip()
    key = (api_key or "").strip()
    if not key:
        return None, "no_api_key"
    if pid not in _LIVE_TTS:
        return None, "not_supported"
    try:
        if pid == "pyai":
            voices = _fetch_pyai(key)
        elif pid == "elevenlabs":
            voices = _fetch_elevenlabs(key)
        elif pid == "cartesia":
            voices = _fetch_cartesia(key)
        else:
            return None, "not_supported"
    except httpx.HTTPStatusError as exc:
        return None, f"http_{exc.response.status_code}"
    except httpx.TimeoutException:
        return None, "timeout"
    except Exception as exc:
        return None, type(exc).__name__
    if not voices:
        return None, "empty_response"
    return voices, None


def api_key_for_tts(provider: str, *, cwd: Path | None = None) -> str | None:
    """Read TTS API key from env (after dotenv load). Never log the value."""
    from wiretap.services.secrets import load_dotenv

    load_dotenv(cwd)
    env = env_for_provider(provider)
    return (os.environ.get(env) or "").strip() or None


def resolve_tts_voices(
    provider: str,
    *,
    api_key: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Resolve voice options: live when key works, else curated fallback.

    Returns ``{voices, default_voice, source, live_supported, error?}`` where
    ``source`` is ``live`` or ``curated``. ``error`` is a short code only
    (never includes the API key).
    """
    pid = (provider or "").lower().strip() or "pyai"
    curated = voices_for_tts(pid)
    default = default_voice_for(pid)
    live_supported = pid in _LIVE_TTS
    key = (api_key or "").strip() or api_key_for_tts(pid, cwd=cwd)

    if key and live_supported:
        live, err = fetch_tts_voices(pid, key)
        if live:
            if default not in {v["id"] for v in live}:
                default = live[0]["id"]
            return {
                "provider": pid,
                "voices": live,
                "default_voice": default,
                "source": "live",
                "live_supported": True,
                "error": None,
            }
        return {
            "provider": pid,
            "voices": curated,
            "default_voice": default,
            "source": "curated",
            "live_supported": True,
            "error": err or "fetch_failed",
        }

    return {
        "provider": pid,
        "voices": curated,
        "default_voice": default,
        "source": "curated",
        "live_supported": live_supported,
        "error": None if key or not live_supported else "no_api_key",
    }


__all__ = [
    "api_key_for_tts",
    "fetch_tts_voices",
    "resolve_tts_voices",
]
