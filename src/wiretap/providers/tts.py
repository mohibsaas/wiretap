"""TTS helpers for LiveKit / transports — delegates to speech factory."""

from __future__ import annotations

import os

from wiretap.providers.factory import build_tts

# OpenAI / PyAI / most adapters emit 24 kHz mono s16le
TTS_SAMPLE_RATE = 24_000


async def synthesize_pcm(
    text: str,
    *,
    voice: str = "alloy",
    provider: str | None = None,
) -> bytes:
    """Return raw PCM16 mono bytes via the configured TTS provider."""
    name = (provider or "").strip()
    if not name:
        name = "pyai" if os.environ.get("PYAI_API_KEY", "").strip() else "openai"
    audio = await build_tts(name, voice).synthesize(text)
    return audio.pcm


__all__ = ["TTS_SAMPLE_RATE", "synthesize_pcm"]
