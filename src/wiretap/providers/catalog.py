"""Provider catalogs for onboarding / suite config.

LLM ids come from LiteLLM (`litellm.models_by_provider`) — **openai first**.
STT/TTS ids follow common Pipecat service names with **pyai first**
(pyai is speech-only: STT/TTS, not an LLM).

Runtime adapters may not implement every id yet — the suite still stores the
choice so a Pipecat worker / LiteLLM call can use it. Secret env names follow
the usual `{PROVIDER}_API_KEY` convention (with a few well-known aliases).
"""

from __future__ import annotations

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


# Pipecat-oriented speech providers (curated; pyai inserted first at runtime).
_PIPECAT_STT = (
    "deepgram",
    "assemblyai",
    "openai",
    "azure",
    "google",
    "groq",
    "aws",
    "gladia",
    "soniox",
    "speechmatics",
)

_PIPECAT_TTS = (
    "cartesia",
    "elevenlabs",
    "openai",
    "deepgram",
    "azure",
    "playht",
    "rime",
    "google",
    "lmnt",
    "aws_polly",
)

# Well-known env aliases (otherwise {ID}_API_KEY uppercased).
_ENV_ALIASES: dict[str, str] = {
    "pyai": "PYAI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "vertex_ai": "VERTEX_AI_API_KEY",
    "azure": "AZURE_API_KEY",
    "bedrock": "AWS_ACCESS_KEY_ID",
    "aws": "AWS_ACCESS_KEY_ID",
    "aws_polly": "AWS_ACCESS_KEY_ID",
    "groq": "GROQ_API_KEY",
    "deepgram": "DEEPGRAM_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "cartesia": "CARTESIA_API_KEY",
    "assemblyai": "ASSEMBLYAI_API_KEY",
    "playht": "PLAYHT_API_KEY",
    "rime": "RIME_API_KEY",
    "lmnt": "LMNT_API_KEY",
    "gladia": "GLADIA_API_KEY",
    "soniox": "SONIOX_API_KEY",
    "speechmatics": "SPEECHMATICS_API_KEY",
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
    "aws_polly": "AWS Polly",
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
    # Capitalize each word for readable dropdown labels
    return " ".join(w[:1].upper() + w[1:] for w in words if w)


@lru_cache(maxsize=1)
def litellm_llm_provider_ids() -> tuple[str, ...]:
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
    # openai first (common default); never include pyai — speech-only
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
        )
        for pid in litellm_llm_provider_ids()
    ]


def stt_providers() -> list[ProviderInfo]:
    ids = ["pyai", *[p for p in _PIPECAT_STT if p != "pyai"]]
    return [
        ProviderInfo(id=pid, label=_label(pid), kind="stt", env=env_for_provider(pid))
        for pid in ids
    ]


def tts_providers() -> list[ProviderInfo]:
    ids = ["pyai", *[p for p in _PIPECAT_TTS if p != "pyai"]]
    return [
        ProviderInfo(id=pid, label=_label(pid), kind="tts", env=env_for_provider(pid))
        for pid in ids
    ]


def provider_catalog() -> dict[str, Any]:
    return {
        "defaults": {"llm": "openai", "stt": "pyai", "tts": "pyai", "voice": "alloy"},
        "llm": [p.__dict__ for p in llm_providers()],
        "stt": [p.__dict__ for p in stt_providers()],
        "tts": [p.__dict__ for p in tts_providers()],
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
    keys = {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "PYAI_API_KEY",
        "RETELL_API_KEY",
        "VAPI_API_KEY",
        "BLAND_API_KEY",
    }
    for p in (*llm_providers(), *stt_providers(), *tts_providers()):
        if p.env.endswith("_API_KEY"):
            keys.add(p.env)
    return tuple(sorted(keys))


__all__ = [
    "ProviderInfo",
    "env_for_provider",
    "llm_providers",
    "managed_secret_keys",
    "known_provider_ids",
    "provider_catalog",
    "stt_providers",
    "tts_providers",
]
