"""TTS helpers for LiveKit / transports — delegates to speech factory."""

from __future__ import annotations

import asyncio
import os

from wiretap.providers.factory import build_tts

# OpenAI / PyAI / most adapters emit 24 kHz mono s16le
TTS_SAMPLE_RATE = 24_000

# Prefetch cache: hide TTS RTT behind agent speech / connect wait.
_pcm_cache: dict[tuple[str, str, str], bytes] = {}
_pcm_inflight: dict[tuple[str, str, str], asyncio.Task[bytes]] = {}
_CACHE_MAX = 32


def _cache_key(text: str, *, voice: str, provider: str) -> tuple[str, str, str]:
    return (provider, voice, text)


def _remember(key: tuple[str, str, str], pcm: bytes) -> bytes:
    if key not in _pcm_cache and len(_pcm_cache) >= _CACHE_MAX:
        # Drop an arbitrary old entry (FIFO-ish via iterator order).
        try:
            del _pcm_cache[next(iter(_pcm_cache))]
        except StopIteration:
            pass
    _pcm_cache[key] = pcm
    return pcm


async def _synthesize_uncached(
    text: str, *, voice: str, provider: str
) -> bytes:
    audio = await build_tts(provider, voice).synthesize(text)
    return audio.pcm


def prefetch_pcm(
    text: str,
    *,
    voice: str = "alloy",
    provider: str | None = None,
) -> asyncio.Task[bytes] | None:
    """Kick off TTS in the background (no-op for empty text)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    name = (provider or "").strip()
    if not name:
        name = "pyai" if os.environ.get("PYAI_API_KEY", "").strip() else "openai"
    key = _cache_key(cleaned, voice=voice or "alloy", provider=name)
    if key in _pcm_cache:
        return None
    existing = _pcm_inflight.get(key)
    if existing is not None and not existing.done():
        return existing

    async def _run() -> bytes:
        try:
            pcm = await _synthesize_uncached(
                cleaned, voice=voice or "alloy", provider=name
            )
            return _remember(key, pcm)
        finally:
            _pcm_inflight.pop(key, None)

    task = asyncio.create_task(_run(), name="tts-prefetch")
    _pcm_inflight[key] = task
    return task


async def synthesize_pcm(
    text: str,
    *,
    voice: str = "alloy",
    provider: str | None = None,
) -> bytes:
    """Return raw PCM16 mono bytes via the configured TTS provider."""
    cleaned = (text or "").strip()
    name = (provider or "").strip()
    if not name:
        name = "pyai" if os.environ.get("PYAI_API_KEY", "").strip() else "openai"
    voice = voice or "alloy"
    if not cleaned:
        return b""
    key = _cache_key(cleaned, voice=voice, provider=name)
    cached = _pcm_cache.get(key)
    if cached is not None:
        return cached
    inflight = _pcm_inflight.get(key)
    if inflight is not None:
        return await inflight
    pcm = await _synthesize_uncached(cleaned, voice=voice, provider=name)
    if len(pcm) < 1000:
        raise RuntimeError(
            f"TTS provider {name!r} returned empty/too-short audio "
            f"({len(pcm)} bytes)"
        )
    return _remember(key, pcm)


def clear_tts_cache() -> None:
    """Test helper."""
    _pcm_cache.clear()
    for task in list(_pcm_inflight.values()):
        task.cancel()
    _pcm_inflight.clear()


__all__ = [
    "TTS_SAMPLE_RATE",
    "clear_tts_cache",
    "prefetch_pcm",
    "synthesize_pcm",
]
