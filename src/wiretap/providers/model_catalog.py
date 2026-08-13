"""Live LLM model catalogs — fetch when an API key is available.

Curated + LiteLLM shortlists in ``catalog.py`` remain the offline fallback.
This module never logs or returns API keys.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from wiretap.providers.catalog import (
    env_for_provider,
    models_for_provider,
)

_TIMEOUT = 5.0
_MAX_MODELS = 40

# Providers with a usable list-models HTTP API.
_LIVE_LLM = frozenset(
    {
        "openai",
        "anthropic",
        "groq",
        "mistral",
        "openrouter",
        "gemini",
        "deepseek",
        "xai",
        "together_ai",
    }
)

_EXCLUDE = (
    "whisper",
    "tts",
    "dall",
    "embed",
    "moderation",
    "realtime",
    "audio",
    "transcribe",
    "image",
    "imagen",
    "veo",
    "computer-use",
    "codex",
    "davinci",
    "babbage",
    "ada-",
    "text-similarity",
    "text-search",
    "edit",
    "instruct-beta",
    "sora",
    "gpt-image",
    "omni-moderation",
)

# Shared with catalog defaults (avoid circular import of private map at module load).
_DEFAULTS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
    "gemini": "gemini/gemini-2.0-flash",
    "groq": "groq/llama-3.3-70b-versatile",
    "mistral": "mistral/mistral-small-latest",
    "deepseek": "deepseek/deepseek-chat",
    "xai": "xai/grok-2",
    "openrouter": "openrouter/auto",
    "together_ai": "together_ai/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
}


def _is_chatty(model_id: str) -> bool:
    low = model_id.lower()
    return not any(tok in low for tok in _EXCLUDE)


def _prefer_rank(model_id: str) -> tuple[int, str]:
    """Lower rank sorts earlier in the picker."""
    low = model_id.lower()
    if any(x in low for x in ("mini", "flash", "haiku", "small", "nano")):
        bucket = 0
    elif any(x in low for x in ("gpt-4o", "sonnet", "claude-3-5", "llama-3.3", "gpt-4.1")):
        bucket = 1
    elif any(x in low for x in ("o4", "o3", "o1", "opus", "pro", "large")):
        bucket = 2
    else:
        bucket = 3
    return (bucket, low)


def _normalize(models: list[str], *, default: str | None, curated: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for mid in models:
        mid = str(mid or "").strip()
        if not mid or mid in seen or not _is_chatty(mid):
            continue
        seen.add(mid)
        cleaned.append(mid)
    cleaned.sort(key=_prefer_rank)

    out: list[str] = []
    for mid in ([default] if default else []) + curated + cleaned:
        if mid and mid not in out and _is_chatty(mid):
            out.append(mid)
        if len(out) >= _MAX_MODELS:
            break
    return out


def _openai_compat_models(
    url: str, api_key: str, *, headers: dict[str, str] | None = None
) -> list[str]:
    hdrs = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(url, headers=hdrs)
        resp.raise_for_status()
        data = resp.json() or {}
    raw = data.get("data") if isinstance(data, dict) else data
    models: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                mid = str(item.get("id") or "").strip()
            else:
                mid = str(item).strip()
            if mid:
                models.append(mid)
    return models


def _fetch_openai(api_key: str) -> list[str]:
    return _openai_compat_models("https://api.openai.com/v1/models", api_key)


def _fetch_anthropic(api_key: str) -> list[str]:
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json() or {}
    raw = data.get("data") or []
    models: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            mid = str(item.get("id") or "").strip()
            if mid:
                models.append(mid)
    return models


def _fetch_groq(api_key: str) -> list[str]:
    models = _openai_compat_models("https://api.groq.com/openai/v1/models", api_key)
    return [m if m.startswith("groq/") else f"groq/{m}" for m in models]


def _fetch_mistral(api_key: str) -> list[str]:
    models = _openai_compat_models("https://api.mistral.ai/v1/models", api_key)
    return [m if m.startswith("mistral/") else f"mistral/{m}" for m in models]


def _fetch_openrouter(api_key: str) -> list[str]:
    models = _openai_compat_models("https://openrouter.ai/api/v1/models", api_key)
    out: list[str] = []
    for m in models:
        out.append(m if m.startswith("openrouter/") else f"openrouter/{m}")
    return out


def _fetch_gemini(api_key: str) -> list[str]:
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
        )
        resp.raise_for_status()
        data = resp.json() or {}
    raw = data.get("models") or []
    models: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()  # models/gemini-2.0-flash
            methods = item.get("supportedGenerationMethods") or []
            if methods and "generateContent" not in methods:
                continue
            mid = name.split("/", 1)[-1] if name else ""
            if mid:
                models.append(f"gemini/{mid}")
    return models


def _fetch_deepseek(api_key: str) -> list[str]:
    models = _openai_compat_models("https://api.deepseek.com/models", api_key)
    return [m if m.startswith("deepseek/") else f"deepseek/{m}" for m in models]


def _fetch_xai(api_key: str) -> list[str]:
    models = _openai_compat_models("https://api.x.ai/v1/models", api_key)
    return [m if m.startswith("xai/") else f"xai/{m}" for m in models]


def _fetch_together(api_key: str) -> list[str]:
    models = _openai_compat_models("https://api.together.xyz/v1/models", api_key)
    return [m if m.startswith("together_ai/") else f"together_ai/{m}" for m in models]


def fetch_llm_models(
    provider: str, api_key: str
) -> tuple[list[str] | None, str | None]:
    """Hit the vendor list-models API. Returns ``(models, error)``."""
    pid = (provider or "").lower().strip()
    key = (api_key or "").strip()
    if not key:
        return None, "no_api_key"
    if pid not in _LIVE_LLM:
        return None, "not_supported"
    try:
        if pid == "openai":
            models = _fetch_openai(key)
        elif pid == "anthropic":
            models = _fetch_anthropic(key)
        elif pid == "groq":
            models = _fetch_groq(key)
        elif pid == "mistral":
            models = _fetch_mistral(key)
        elif pid == "openrouter":
            models = _fetch_openrouter(key)
        elif pid == "gemini":
            models = _fetch_gemini(key)
        elif pid == "deepseek":
            models = _fetch_deepseek(key)
        elif pid == "xai":
            models = _fetch_xai(key)
        elif pid == "together_ai":
            models = _fetch_together(key)
        else:
            return None, "not_supported"
    except httpx.HTTPStatusError as exc:
        return None, f"http_{exc.response.status_code}"
    except httpx.TimeoutException:
        return None, "timeout"
    except Exception as exc:
        return None, type(exc).__name__
    if not models:
        return None, "empty_response"
    models = [m for m in models if _is_chatty(m)]
    if not models:
        return None, "empty_response"
    return models, None


def api_key_for_llm(provider: str, *, cwd: Path | None = None) -> str | None:
    from wiretap.services.secrets import load_dotenv

    load_dotenv(cwd)
    env = env_for_provider(provider)
    return (os.environ.get(env) or "").strip() or None


def resolve_llm_models(
    provider: str,
    *,
    api_key: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Resolve model options: live when key works, else curated/LiteLLM fallback."""
    pid = (provider or "").lower().strip() or "openai"
    curated = models_for_provider(pid)
    default = _DEFAULTS.get(pid) or (curated[0] if curated else "gpt-4o-mini")
    live_supported = pid in _LIVE_LLM
    key = (api_key or "").strip() or api_key_for_llm(pid, cwd=cwd)

    if key and live_supported:
        live, err = fetch_llm_models(pid, key)
        if live:
            models = _normalize(live, default=default, curated=curated[:6])
            return {
                "provider": pid,
                "models": models,
                "default_model": default if default in models else models[0],
                "source": "live",
                "live_supported": True,
                "error": None,
            }
        return {
            "provider": pid,
            "models": curated,
            "default_model": default,
            "source": "curated",
            "live_supported": True,
            "error": err or "fetch_failed",
        }

    return {
        "provider": pid,
        "models": curated,
        "default_model": default,
        "source": "curated",
        "live_supported": live_supported,
        "error": None if key or not live_supported else "no_api_key",
    }


__all__ = [
    "api_key_for_llm",
    "fetch_llm_models",
    "resolve_llm_models",
]
