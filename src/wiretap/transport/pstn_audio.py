"""PCM ↔ telephony audio for the PSTN transport.

The SIP layer speaks 8-bit unsigned linear PCM at 8 kHz — that is what pyVoIP
hands to and takes from its RTP clients, which own the µ-law encoding. Wiretap's
speech providers speak signed 16-bit PCM. Kept dependency-free so it stays
testable without the ``pstn`` extra installed.
"""

from __future__ import annotations

import array

from wiretap.transport.audio_util import downsample_pcm16, upsample_pcm16

PSTN_SAMPLE_RATE = 8_000
STT_SAMPLE_RATE = 16_000
# 20 ms at 8 kHz — one RTP frame.
FRAME_BYTES = 160
# Zero amplitude in 8-bit unsigned linear; pyVoIP pads short reads with it.
SILENCE_BYTE = 0x80
# A telephony line is never digitally silent, so idle detection is energy-based.
SPEECH_PEAK_THRESHOLD = 900


def pcm16_to_pstn(pcm16: bytes, *, sample_rate: int) -> bytes:
    """Signed 16-bit PCM at ``sample_rate`` → 8-bit unsigned linear at 8 kHz."""
    narrowed = downsample_pcm16(pcm16, sample_rate, PSTN_SAMPLE_RATE)
    samples = array.array("h")
    samples.frombytes(narrowed[: len(narrowed) - (len(narrowed) % 2)])
    return bytes((sample >> 8) + 128 for sample in samples)


def pstn_to_pcm16(payload: bytes) -> bytes:
    """8-bit unsigned linear at 8 kHz → signed 16-bit PCM at 16 kHz."""
    if not payload:
        return b""
    samples = array.array("h", ((byte - 128) << 8 for byte in payload))
    return upsample_pcm16(samples.tobytes(), PSTN_SAMPLE_RATE, STT_SAMPLE_RATE)


def peak_amplitude(pcm16: bytes) -> int:
    """Loudest absolute sample, for the voice-activity gate."""
    samples = array.array("h")
    samples.frombytes(pcm16[: len(pcm16) - (len(pcm16) % 2)])
    if not samples:
        return 0
    return max(abs(sample) for sample in samples)


def is_speech(pcm16: bytes, *, threshold: int = SPEECH_PEAK_THRESHOLD) -> bool:
    return peak_amplitude(pcm16) > threshold


def is_starved_read(payload: bytes) -> bool:
    """True when pyVoIP had no RTP left and padded the read with silence bytes.

    A live line carries comfort noise, so an exactly-uniform block means the jitter
    buffer is empty rather than that the caller went quiet. pyVoIP's own blocking
    read uses the same signal to decide it has caught up.
    """
    return not payload or payload == bytes([SILENCE_BYTE]) * len(payload)


__all__ = [
    "FRAME_BYTES",
    "PSTN_SAMPLE_RATE",
    "SILENCE_BYTE",
    "SPEECH_PEAK_THRESHOLD",
    "STT_SAMPLE_RATE",
    "is_speech",
    "is_starved_read",
    "pcm16_to_pstn",
    "peak_amplitude",
    "pstn_to_pcm16",
]
