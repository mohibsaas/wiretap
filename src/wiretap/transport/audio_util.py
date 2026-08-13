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


def upsample_pcm16(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """PCM16 mono upsample by linear interpolation.

    Sample-and-hold is cheaper but leaves a stair-stepped waveform whose
    high-frequency images degrade transcription of already narrowband
    telephony audio.
    """
    if src_rate == dst_rate or not pcm:
        return pcm
    if src_rate <= 0 or dst_rate <= 0:
        raise ValueError("sample rates must be positive")
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return b""
    step = src_rate / dst_rate
    last = len(samples) - 1
    out = array.array("h")
    for i in range(int(len(samples) / step)):
        position = i * step
        left = int(position)
        right = min(left + 1, last)
        weight = position - left
        out.append(round(samples[left] + (samples[right] - samples[left]) * weight))
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
