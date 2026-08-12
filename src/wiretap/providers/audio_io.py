"""PCM / WAV helpers for speech adapters."""

from __future__ import annotations

import io
import wave


def pcm_s16le_to_wav(pcm: bytes, *, sample_rate: int, channels: int = 1) -> bytes:
    """Wrap raw PCM16 little-endian mono/stereo as a WAV blob."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def wav_to_pcm_s16le(wav_bytes: bytes) -> tuple[bytes, int, int]:
    """Return (pcm, sample_rate, channels) from a WAV blob."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    return pcm, rate, channels


__all__ = ["pcm_s16le_to_wav", "wav_to_pcm_s16le"]
