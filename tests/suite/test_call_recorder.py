"""CallRecorder timeline helpers."""

from wiretap.suite.audio import CallRecorder


def test_elapsed_ms_tracks_pcm_bytes() -> None:
    rec = CallRecorder(sample_rate=16_000)
    assert rec.elapsed_ms() == 0.0
    # 16000 samples * 2 bytes = 1 second
    rec.add(b"\x00\x00" * 16_000)
    assert abs(rec.elapsed_ms() - 1000.0) < 0.01
    rec.add(b"\x00\x00" * 8_000)
    assert abs(rec.elapsed_ms() - 1500.0) < 0.01
