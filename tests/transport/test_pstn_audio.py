"""Telephony audio conversion for the PSTN transport."""

from __future__ import annotations

import array
import math

from wiretap.transport.audio_util import downsample_pcm16, upsample_pcm16
from wiretap.transport.pstn_audio import (
    PSTN_SAMPLE_RATE,
    SILENCE_BYTE,
    STT_SAMPLE_RATE,
    is_speech,
    is_starved_read,
    pcm16_to_pstn,
    peak_amplitude,
    pstn_to_pcm16,
)


def _tone(samples: int, *, amplitude: int, rate: int = PSTN_SAMPLE_RATE) -> bytes:
    values = array.array(
        "h",
        (
            int(amplitude * math.sin(2 * math.pi * 440 * i / rate))
            for i in range(samples)
        ),
    )
    return values.tobytes()


def test_pcm16_to_pstn_is_one_byte_per_8k_sample() -> None:
    pcm = _tone(800, amplitude=20_000)

    payload = pcm16_to_pstn(pcm, sample_rate=PSTN_SAMPLE_RATE)

    assert len(payload) == 800
    assert all(0 <= byte <= 255 for byte in payload)


def test_pcm16_to_pstn_downsamples_from_tts_rate() -> None:
    """OpenAI-style TTS is 24 kHz; the line is 8 kHz."""
    pcm = _tone(2_400, amplitude=12_000, rate=24_000)

    payload = pcm16_to_pstn(pcm, sample_rate=24_000)

    assert len(payload) == 800


def test_silence_maps_to_the_byte_pyvoip_pads_with() -> None:
    silent = array.array("h", [0] * 160).tobytes()

    assert set(pcm16_to_pstn(silent, sample_rate=PSTN_SAMPLE_RATE)) == {SILENCE_BYTE}


def test_pstn_to_pcm16_upsamples_to_the_stt_rate() -> None:
    payload = bytes([SILENCE_BYTE] * 160)

    pcm = pstn_to_pcm16(payload)

    # 160 bytes at 8 kHz → 320 samples at 16 kHz → 640 bytes of PCM16.
    assert len(pcm) == 640
    assert peak_amplitude(pcm) == 0


def test_round_trip_preserves_the_waveform_within_8_bit_resolution() -> None:
    """The line is 8-bit, so only the top byte of each sample survives."""
    original = _tone(400, amplitude=24_000)

    restored = pstn_to_pcm16(pcm16_to_pstn(original, sample_rate=PSTN_SAMPLE_RATE))
    back_to_8k = downsample_pcm16(restored, STT_SAMPLE_RATE, PSTN_SAMPLE_RATE)

    before = array.array("h")
    before.frombytes(original)
    after = array.array("h")
    after.frombytes(back_to_8k)
    assert len(after) == len(before)
    assert max(abs(a - b) for a, b in zip(before, after, strict=True)) <= 256


def test_energy_gate_separates_line_noise_from_speech() -> None:
    noise = _tone(800, amplitude=200)
    speech = _tone(800, amplitude=8_000)

    assert not is_speech(noise)
    assert is_speech(speech)


def test_peak_amplitude_ignores_a_trailing_odd_byte() -> None:
    assert peak_amplitude(b"") == 0
    assert peak_amplitude(b"\x00") == 0


def test_upsample_is_a_no_op_at_the_same_rate() -> None:
    pcm = _tone(80, amplitude=1_000)

    assert upsample_pcm16(pcm, 16_000, 16_000) == pcm


def test_starved_reads_are_told_apart_from_line_audio() -> None:
    # pyVoIP pads a read it could not satisfy with SILENCE_BYTE.
    assert is_starved_read(b"")
    assert is_starved_read(bytes([SILENCE_BYTE]) * 800)
    # A live line carries comfort noise, so it is never exactly uniform.
    assert not is_starved_read(bytes([SILENCE_BYTE]) * 799 + b"\x81")


def test_upsampling_interpolates_rather_than_holding_samples() -> None:
    """Stair-stepped audio carries HF images that hurt narrowband transcription."""
    pcm = array.array("h", [0, 1_000]).tobytes()

    out = array.array("h")
    out.frombytes(upsample_pcm16(pcm, PSTN_SAMPLE_RATE, STT_SAMPLE_RATE))

    assert list(out) == [0, 500, 1_000, 1_000]
