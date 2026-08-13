"""Provider catalogs for onboarding / suite config.

LLM ids come from LiteLLM (`litellm.models_by_provider`) — **openai first**.
STT/TTS ids are curated speech providers with **pyai first**
(pyai is speech-only: STT/TTS, not an LLM).

Models and TTS voices are **curated shortlists** (not live vendor fetches during
init). Users can still type a custom model / voice id in CLI and UI.

Runtime adapters may not implement every id yet — the suite still stores the
choice. Secret env names follow `{PROVIDER}_API_KEY` (with a few well-known aliases).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    kind: str  # llm | stt | tts
    env: str
    default_model: str | None = None
    models: tuple[str, ...] = ()
    default_voice: str | None = None
    voices: tuple[dict[str, str], ...] = ()


# Speech providers that have working adapters in factory.py (pyai first at runtime).
_SPEECH_STT = (
    "deepgram",
    "elevenlabs",
    "assemblyai",
    "openai",
    "groq",
    "gladia",
)

_SPEECH_TTS = (
    "cartesia",
    "elevenlabs",
    "openai",
    "deepgram",
    "playht",
    "rime",
    "lmnt",
)

# Well-known env aliases (otherwise {ID}_API_KEY uppercased).
_ENV_ALIASES: dict[str, str] = {
    "pyai": "PYAI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "vertex_ai": "VERTEX_AI_API_KEY",
    "bedrock": "AWS_ACCESS_KEY_ID",
    "groq": "GROQ_API_KEY",
    "deepgram": "DEEPGRAM_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "cartesia": "CARTESIA_API_KEY",
    "assemblyai": "ASSEMBLYAI_API_KEY",
    "playht": "PLAYHT_API_KEY",
    "rime": "RIME_API_KEY",
    "lmnt": "LMNT_API_KEY",
    "gladia": "GLADIA_API_KEY",
    "together_ai": "TOGETHERAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "COHERE_API_KEY",
    "xai": "XAI_API_KEY",
    "fireworks_ai": "FIREWORKS_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "ollama": "OLLAMA_API_KEY",
    "huggingface": "HUGGINGFACE_API_KEY",
}

_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
    "gemini": "gemini/gemini-2.0-flash",
    "groq": "groq/llama-3.3-70b-versatile",
    "mistral": "mistral/mistral-small-latest",
    "deepseek": "deepseek/deepseek-chat",
    "xai": "xai/grok-2",
    "openrouter": "openrouter/auto",
    "ollama": "ollama/llama3.2",
}

# Curated chat models shown in CLI/UI (LiteLLM's full list includes image/audio junk).
_CURATED_MODELS: dict[str, tuple[str, ...]] = {
    "openai": (
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1-mini",
        "gpt-4.1",
        "o4-mini",
        "o3-mini",
    ),
    "anthropic": (
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
        "claude-sonnet-4-5",
        "claude-opus-4-5",
        "claude-haiku-4-5-20251001",
    ),
    "gemini": (
        "gemini/gemini-2.0-flash",
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.5-pro",
        "gemini/gemini-flash-latest",
    ),
    "groq": (
        "groq/llama-3.3-70b-versatile",
        "groq/llama-3.1-8b-instant",
        "groq/openai/gpt-oss-120b",
        "groq/qwen/qwen3-32b",
    ),
    "mistral": (
        "mistral/mistral-small-latest",
        "mistral/mistral-large-latest",
        "mistral/mistral-medium-latest",
    ),
    "openrouter": (
        "openrouter/auto",
        "openrouter/openai/gpt-4o-mini",
        "openrouter/anthropic/claude-3.5-sonnet",
        "openrouter/google/gemini-2.0-flash-001",
    ),
    "deepseek": ("deepseek/deepseek-chat", "deepseek/deepseek-reasoner"),
    "xai": ("xai/grok-2", "xai/grok-3-mini"),
    "ollama": ("ollama/llama3.2", "ollama/mistral", "ollama/qwen2.5"),
    "together_ai": (
        "together_ai/meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        "together_ai/meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    ),
}


def _voice(vid: str, label: str) -> dict[str, str]:
    return {"id": vid, "label": label}


# OpenAI TTS presets (also accepted by PyAI as drop-in aliases).
_OPENAI_PRESET_VOICES: tuple[dict[str, str], ...] = (
    _voice("alloy", "Alloy"),
    _voice("ash", "Ash"),
    _voice("ballad", "Ballad"),
    _voice("coral", "Coral"),
    _voice("echo", "Echo"),
    _voice("fable", "Fable"),
    _voice("onyx", "Onyx"),
    _voice("nova", "Nova"),
    _voice("sage", "Sage"),
    _voice("shimmer", "Shimmer"),
    _voice("verse", "Verse"),
)

# Curated TTS voices — ids must match what factory.py sends to each vendor.
_TTS_VOICES: dict[str, tuple[dict[str, str], ...]] = {
    "openai": _OPENAI_PRESET_VOICES,
    "pyai": (
        *_OPENAI_PRESET_VOICES,
        _voice("stock_ava_en_us", "Ava (stock)"),
        _voice("stock_dorit_en_us", "Dorit (stock)"),
    ),
    "elevenlabs": (
        _voice("21m00Tcm4TlvDq8ikWAM", "Rachel"),
        _voice("AZnzlk1XvdvUeBnXmlld", "Domi"),
        _voice("EXAVITQu4vr4xnSDxMaL", "Bella"),
        _voice("ErXwobaYiN019PkySvjV", "Antoni"),
        _voice("MF3mGyEYCl7XYWbV9V6O", "Elli"),
        _voice("TxGEqnHWrfWFTfGW9XjX", "Josh"),
        _voice("VR6AewLTigWG4xSOukaG", "Arnold"),
        _voice("pNInz6obpgDQGcFmaJgB", "Adam"),
        _voice("yoZ06aMxZJJ28mfd3POQ", "Sam"),
    ),
    "cartesia": (
        _voice("79a125e8-cd45-4c13-8a67-188112f4dd22", "Default (sonic)"),
        _voice("a0e99841-438c-4a64-b679-ae501e7d6091", "Barbershop Man"),
        _voice("248be419-c339-4f94-8b0d-e79e2288ac2d", "Helpful Woman"),
    ),
    # Deepgram Speak uses model id as the "voice".
    "deepgram": (
        _voice("aura-asteria-en", "Asteria"),
        _voice("aura-luna-en", "Luna"),
        _voice("aura-stella-en", "Stella"),
        _voice("aura-athena-en", "Athena"),
        _voice("aura-hera-en", "Hera"),
        _voice("aura-orion-en", "Orion"),
        _voice("aura-arcas-en", "Arcas"),
        _voice("aura-perseus-en", "Perseus"),
        _voice("aura-angus-en", "Angus"),
        _voice("aura-orpheus-en", "Orpheus"),
        _voice("aura-helios-en", "Helios"),
        _voice("aura-zeus-en", "Zeus"),
    ),
    "lmnt": (
        _voice("lily", "Lily"),
        _voice("daniel", "Daniel"),
        _voice("amy", "Amy"),
        _voice("marcus", "Marcus"),
    ),
    "rime": (
        _voice("luna", "Luna"),
        _voice("celeste", "Celeste"),
        _voice("ursa", "Ursa"),
    ),
    "playht": (
        _voice(
            "s3://voice-cloning-zero-shot/d9ff78ba-d016-47f6-b0ef-dd630f59414e/female-cs/manifest.json",
            "Jennifer (default)",
        ),
    ),
}

_DEFAULT_VOICES: dict[str, str] = {
    "openai": "alloy",
    "pyai": "alloy",  # OpenAI-compat alias; also accepts stock_* ids
    "elevenlabs": "21m00Tcm4TlvDq8ikWAM",
    "cartesia": "79a125e8-cd45-4c13-8a67-188112f4dd22",
    "deepgram": "aura-asteria-en",
    "lmnt": "lily",
    "rime": "luna",
    "playht": (
        "s3://voice-cloning-zero-shot/d9ff78ba-d016-47f6-b0ef-dd630f59414e/"
        "female-cs/manifest.json"
    ),
}


def env_for_provider(provider_id: str) -> str:
    pid = (provider_id or "").lower().strip()
    if pid in _ENV_ALIASES:
        return _ENV_ALIASES[pid]
    safe = "".join(c if c.isalnum() else "_" for c in pid).upper()
    return f"{safe}_API_KEY"


_LABEL_OVERRIDES: dict[str, str] = {
    "pyai": "PyAI",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "deepgram": "Deepgram",
    "elevenlabs": "ElevenLabs",
    "cartesia": "Cartesia",
    "assemblyai": "AssemblyAI",
    "together_ai": "Together AI",
    "fireworks_ai": "Fireworks AI",
    "openrouter": "OpenRouter",
    "vertex_ai": "Vertex AI",
    "huggingface": "Hugging Face",
    "playht": "PlayHT",
    "xai": "xAI",
}


def _label(provider_id: str) -> str:
    pid = (provider_id or "").lower().strip()
    if pid in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[pid]
    words = pid.replace("_", " ").split()
    if not words:
        return provider_id
    return " ".join(w[:1].upper() + w[1:] for w in words if w)


def models_for_provider(provider_id: str) -> list[str]:
    """Curated simulator/judge model shortlist for a LiteLLM provider.

    Merges our curated defaults with a filtered slice of LiteLLM's local
    ``models_by_provider`` map (no network). Image/audio/embedding ids are dropped.
    """
    pid = (provider_id or "").lower().strip()
    default = _DEFAULT_MODELS.get(pid)
    curated = list(_CURATED_MODELS.get(pid) or ())
    out: list[str] = []
    if default:
        out.append(default)
    for mid in curated:
        if mid not in out:
            out.append(mid)
    for mid in _litellm_chat_models(pid):
        if mid not in out:
            out.append(mid)
        if len(out) >= 16:
            break
    return out[:16]


_LITELLM_EXCLUDE = (
    "image",
    "dall",
    "tts",
    "whisper",
    "embed",
    "moderation",
    "audio",
    "realtime",
    "transcribe",
    "veo",
    "imagen",
    "1024-x",
    "computer-use",
    "codex",
)


def _litellm_chat_models(provider_id: str) -> list[str]:
    pid = (provider_id or "").lower().strip()
    try:
        import litellm

        raw = list(litellm.models_by_provider.get(pid) or [])
    except Exception:
        return []
    out: list[str] = []
    for item in raw:
        mid = str(item).strip()
        low = mid.lower()
        if not mid or any(tok in low for tok in _LITELLM_EXCLUDE):
            continue
        out.append(mid)
        if len(out) >= 24:
            break
    return out


def voices_for_tts(provider_id: str) -> list[dict[str, str]]:
    pid = (provider_id or "").lower().strip()
    return [dict(v) for v in _TTS_VOICES.get(pid, ())]


def default_voice_for(provider_id: str) -> str:
    pid = (provider_id or "").lower().strip()
    if pid in _DEFAULT_VOICES:
        return _DEFAULT_VOICES[pid]
    voices = _TTS_VOICES.get(pid) or ()
    if voices:
        return voices[0]["id"]
    return "alloy"


@lru_cache(maxsize=1)
def litellm_llm_provider_ids() -> tuple[str, ...]:
    # Avoid LiteLLM's cold-start HTTP fetch of the public model cost map
    # (multi-second hang on `wiretap status` / first catalog load).
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    try:
        import litellm

        ids = sorted(str(k).lower() for k in litellm.models_by_provider.keys())
    except Exception:
        ids = [
            "openai",
            "anthropic",
            "gemini",
            "groq",
            "mistral",
            "azure",
            "bedrock",
            "together_ai",
            "openrouter",
            "ollama",
            "deepseek",
            "xai",
        ]
    out: list[str] = ["openai"]
    for pid in ids:
        if pid in {"pyai", "openai"}:
            continue
        if pid not in out:
            out.append(pid)
    return tuple(out)


def llm_providers() -> list[ProviderInfo]:
    return [
        ProviderInfo(
            id=pid,
            label=_label(pid),
            kind="llm",
            env=env_for_provider(pid),
            default_model=_DEFAULT_MODELS.get(pid) or f"{pid}/default",
            models=tuple(models_for_provider(pid)),
        )
        for pid in litellm_llm_provider_ids()
    ]


def stt_providers() -> list[ProviderInfo]:
    ids = ["pyai", *[p for p in _SPEECH_STT if p != "pyai"]]
    return [
        ProviderInfo(id=pid, label=_label(pid), kind="stt", env=env_for_provider(pid))
        for pid in ids
    ]


def tts_providers() -> list[ProviderInfo]:
    ids = ["pyai", *[p for p in _SPEECH_TTS if p != "pyai"]]
    return [
        ProviderInfo(
            id=pid,
            label=_label(pid),
            kind="tts",
            env=env_for_provider(pid),
            default_voice=default_voice_for(pid),
            voices=tuple(voices_for_tts(pid)),
        )
        for pid in ids
    ]


@lru_cache(maxsize=1)
def provider_catalog() -> dict[str, Any]:
    tts = tts_providers()
    default_tts = "pyai"
    return {
        "defaults": {
            "llm": "openai",
            "stt": "pyai",
            "tts": default_tts,
            "voice": default_voice_for(default_tts),
        },
        "llm": [
            {
                **{k: v for k, v in p.__dict__.items() if k not in {"voices"}},
                "models": list(p.models),
            }
            for p in llm_providers()
        ],
        "stt": [p.__dict__ for p in stt_providers()],
        "tts": [
            {
                **{k: v for k, v in p.__dict__.items() if k not in {"models"}},
                "voices": [dict(v) for v in p.voices],
                "default_voice": p.default_voice,
            }
            for p in tts
        ],
    }


def known_provider_ids(kind: str) -> set[str]:
    kind = kind.lower()
    if kind == "llm":
        return {p.id for p in llm_providers()}
    if kind == "stt":
        return {p.id for p in stt_providers()}
    if kind == "tts":
        return {p.id for p in tts_providers()}
    raise ValueError(f"unknown kind: {kind}")


def managed_secret_keys() -> tuple[str, ...]:
    """Env keys the UI may write — no LiteLLM import (keeps CLI fast)."""
    keys = {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "PYAI_API_KEY",
        "RETELL_API_KEY",
        "VAPI_API_KEY",
        "BLAND_API_KEY",
        "SYNTHFLOW_API_KEY",
        "BOLNA_API_KEY",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "LIVEKIT_TOKEN",
        "LIVEKIT_URL",
        "SYNTHFLOW_FROM_NUMBER",
        "SYNTHFLOW_TO_NUMBER",
        "PLAYHT_USER_ID",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_SIP_PASSWORD",
        "TWILIO_FROM_NUMBER",
    }
    keys.update(v for v in _ENV_ALIASES.values() if v.endswith("_API_KEY") or v.endswith("_KEY_ID"))
    for pid in (*_SPEECH_STT, *_SPEECH_TTS, "pyai"):
        env = env_for_provider(pid)
        if env.endswith("_API_KEY"):
            keys.add(env)
    return tuple(sorted(keys))


__all__ = [
    "ProviderInfo",
    "default_voice_for",
    "env_for_provider",
    "llm_providers",
    "managed_secret_keys",
    "models_for_provider",
    "known_provider_ids",
    "provider_catalog",
    "stt_providers",
    "tts_providers",
    "voices_for_tts",
]
