"""Speech factory tests (no live network)."""

from __future__ import annotations

import pytest

from wiretap.providers.audio_io import pcm_s16le_to_wav, wav_to_pcm_s16le
from wiretap.providers.factory import build_stt, build_tts


def test_pcm_wav_roundtrip() -> None:
    pcm = b"\x01\x00\x02\x00\x03\x00\x04\x00"
    wav = pcm_s16le_to_wav(pcm, sample_rate=16_000)
    out, rate, ch = wav_to_pcm_s16le(wav)
    assert rate == 16_000
    assert ch == 1
    assert out == pcm


def test_build_tts_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPGRAM_API_KEY"):
        build_tts("deepgram")


def test_build_stt_known_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "aa-test")
    monkeypatch.setenv("GLADIA_API_KEY", "gl-test")
    monkeypatch.setenv("GROQ_API_KEY", "gq-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("PYAI_API_KEY", "py-test")
    assert build_stt("deepgram").__class__.__name__ == "DeepgramSTT"
    assert build_stt("assemblyai").__class__.__name__ == "AssemblyAISTT"
    assert build_stt("gladia").__class__.__name__ == "GladiaSTT"
    assert build_stt("groq").__class__.__name__ == "GroqSTT"
    assert build_stt("openai").__class__.__name__ == "OpenAICompatSTT"
    assert build_stt("pyai").__class__.__name__ == "OpenAICompatSTT"


def test_build_tts_known_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARTESIA_API_KEY", "c-test")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "e-test")
    monkeypatch.setenv("LMNT_API_KEY", "l-test")
    monkeypatch.setenv("RIME_API_KEY", "r-test")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert build_tts("cartesia").__class__.__name__ == "CartesiaTTS"
    assert build_tts("elevenlabs").__class__.__name__ == "ElevenLabsTTS"
    assert build_tts("lmnt").__class__.__name__ == "LmntTTS"
    assert build_tts("rime").__class__.__name__ == "RimeTTS"
    assert build_tts("deepgram").__class__.__name__ == "DeepgramTTS"


def test_unsupported_cloud_providers() -> None:
    with pytest.raises(ValueError, match="Unknown STT"):
        build_stt("azure")
    with pytest.raises(ValueError, match="Unknown TTS"):
        build_tts("google")
    with pytest.raises(ValueError, match="Unknown STT"):
        build_stt("soniox")
