"""PCM padding helpers."""

from __future__ import annotations

from wiretap.transport.audio_util import pad_pcm16_silence, silence_pcm16


def test_pad_pcm16_silence_adds_lead_and_trail() -> None:
    pcm = b"\x01\x00" * 100
    out = pad_pcm16_silence(pcm, sample_rate=16_000, lead_s=0.01, trail_s=0.02)
    lead = silence_pcm16(0.01, sample_rate=16_000)
    trail = silence_pcm16(0.02, sample_rate=16_000)
    assert out.startswith(lead)
    assert out.endswith(trail)
    assert len(out) == len(lead) + len(pcm) + len(trail)
