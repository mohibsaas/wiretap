"""Shared PCM helpers for voice transports."""

from __future__ import annotations

import array
import struct


def downsample_pcm16(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Naive PCM16 mono downsample (drop/average samples)."""
    if src_rate == dst_rate or not pcm:
        return pcm
    if src_rate <= 0 or dst_rate <= 0:
        raise ValueError("sample rates must be positive")
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return b""
    ratio = src_rate / dst_rate
    out = array.array("h")
    i = 0.0
    while int(i) < len(samples):
        out.append(samples[int(i)])
        i += ratio
    return out.tobytes()


def pcm16le_to_be(pcm_le: bytes) -> bytes:
    """Convert little-endian PCM16 to big-endian (Synthflow L16)."""
    n = len(pcm_le) - (len(pcm_le) % 2)
    out = bytearray(n)
    for i in range(0, n, 2):
        (sample,) = struct.unpack_from("<h", pcm_le, i)
        struct.pack_into(">h", out, i, sample)
    return bytes(out)


def pcm16be_to_le(pcm_be: bytes) -> bytes:
    n = len(pcm_be) - (len(pcm_be) % 2)
    out = bytearray(n)
    for i in range(0, n, 2):
        (sample,) = struct.unpack_from(">h", pcm_be, i)
        struct.pack_into("<h", out, i, sample)
    return bytes(out)


def silence_pcm16(duration_s: float, *, sample_rate: int) -> bytes:
    """Zero PCM16 mono for ``duration_s`` seconds."""
    if duration_s <= 0 or sample_rate <= 0:
        return b""
    n = int(sample_rate * duration_s)
    return b"\x00\x00" * max(0, n)


def pad_pcm16_silence(
    pcm: bytes,
    *,
    sample_rate: int,
    lead_s: float = 0.08,
    trail_s: float = 0.15,
) -> bytes:
    """Pad leading/trailing silence so remote VADs reliably detect caller speech.

    Provider-agnostic helper for Retell/LiveKit/Vapi/Synthflow/ElevenLabs publish.
    """
    if not pcm:
        return pcm
    return (
        silence_pcm16(lead_s, sample_rate=sample_rate)
        + pcm
        + silence_pcm16(trail_s, sample_rate=sample_rate)
    )


__all__ = [
    "downsample_pcm16",
    "pad_pcm16_silence",
    "pcm16be_to_le",
    "pcm16le_to_be",
    "silence_pcm16",
]
