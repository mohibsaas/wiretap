"""Record and persist call audio (PCM → WAV) for evaluation playback."""

from __future__ import annotations

import wave
from dataclasses import dataclass, field
from pathlib import Path

from wiretap.paths import ensure_layout, simulations_dir, wiretap_root


@dataclass
class CallRecorder:
    """Append-only mono PCM16 buffer for one simulation."""

    sample_rate: int = 16_000
    _chunks: list[bytes] = field(default_factory=list)
    _nbytes: int = field(default=0, init=False, repr=False)

    def add(self, pcm: bytes, *, sample_rate: int | None = None) -> None:
        if not pcm:
            return
        rate = sample_rate or self.sample_rate
        if rate != self.sample_rate:
            pcm = _resample_pcm16(pcm, rate, self.sample_rate)
        # Align to 2-byte frames
        if len(pcm) % 2:
            pcm = pcm[:-1]
        if pcm:
            self._chunks.append(pcm)
            self._nbytes += len(pcm)

    def empty(self) -> bool:
        return self._nbytes == 0

    def pcm(self) -> bytes:
        return b"".join(self._chunks)

    def elapsed_ms(self) -> float:
        """Milliseconds of audio currently buffered (WAV playhead offset)."""
        if self._nbytes <= 0 or self.sample_rate <= 0:
            return 0.0
        # PCM16 mono: 2 bytes per sample
        return (self._nbytes / 2.0 / float(self.sample_rate)) * 1000.0

    def write_wav(self, path: Path) -> Path | None:
        data = self.pcm()
        if not data:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(data)
        return path


def audio_dir(cwd: Path | None = None) -> Path:
    return simulations_dir(cwd) / "audio"


def save_call_audio(
    simulation_id: str,
    recorder: CallRecorder,
    cwd: Path | None = None,
) -> str | None:
    """Write WAV under .wiretap/simulations/audio/. Returns path relative to .wiretap/."""
    if recorder.empty() or not simulation_id:
        return None
    ensure_layout(cwd)
    dest = audio_dir(cwd) / f"{simulation_id}.wav"
    written = recorder.write_wav(dest)
    if not written:
        return None
    root = wiretap_root(cwd)
    try:
        return str(written.relative_to(root))
    except ValueError:
        return str(written)


def resolve_audio_path(rel_or_abs: str, cwd: Path | None = None) -> Path | None:
    raw = Path(rel_or_abs)
    if raw.is_file():
        return raw
    candidate = wiretap_root(cwd) / rel_or_abs
    if candidate.is_file():
        return candidate
    return None


def _resample_pcm16(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate or not pcm:
        return pcm
    import array

    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return b""
    out = array.array("h")
    # Linear nearest-neighbor for MVP
    n_out = max(1, int(len(samples) * dst_rate / src_rate))
    for i in range(n_out):
        src_i = min(len(samples) - 1, int(i * src_rate / dst_rate))
        out.append(samples[src_i])
    return out.tobytes()


__all__ = [
    "CallRecorder",
    "audio_dir",
    "resolve_audio_path",
    "save_call_audio",
]
