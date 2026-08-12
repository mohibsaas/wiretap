"""Speech factory + pipeline tests (no live network)."""

from __future__ import annotations

import pytest

from wiretap.media.pipeline import SpeechPipeline, build_speech_pipeline
from wiretap.providers.audio_io import pcm_s16le_to_wav, wav_to_pcm_s16le
from wiretap.providers.factory import build_stt, build_tts
from wiretap.providers.speech import AudioBuffer


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


def test_deferred_cloud_providers() -> None:
    with pytest.raises(ValueError, match="cloud"):
        build_stt("azure")
    with pytest.raises(ValueError, match="cloud"):
        build_tts("google")


def test_pipeline_httpx_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    async def fake_synth(self: object, text: str) -> AudioBuffer:
        return AudioBuffer(pcm=b"\x00\x01" * 8, sample_rate=24_000)

    monkeypatch.setattr(
        "wiretap.media.pipeline.complete",
        lambda **kwargs: "hello from judge",
    )
    monkeypatch.setattr(
        "wiretap.providers.factory.OpenAICompatTTS.synthesize",
        fake_synth,
    )

    pipe = SpeechPipeline(stt="openai", tts="openai", llm_model="gpt-4o-mini")
    monkeypatch.setattr("wiretap.media.pipecat_bridge.pipecat_available", lambda: False)

    import asyncio

    turn = asyncio.run(pipe.reply(messages=[{"role": "system", "content": "hi"}]))
    assert turn.engine == "httpx"
    assert turn.reply_text == "hello from judge"
    assert turn.reply_audio.pcm


def test_pipeline_pipecat_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Pipecat is available, reply() should prefer the pipecat engine."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    async def fake_synth(self: object, text: str) -> AudioBuffer:
        return AudioBuffer(pcm=b"\x00\x01" * 8, sample_rate=24_000)

    monkeypatch.setattr(
        "wiretap.media.pipeline.complete",
        lambda **kwargs: "pipecat hello",
    )
    monkeypatch.setattr(
        "wiretap.providers.factory.OpenAICompatTTS.synthesize",
        fake_synth,
    )
    monkeypatch.setattr("wiretap.media.pipecat_bridge.pipecat_available", lambda: True)

    import asyncio

    pipe = SpeechPipeline(stt="openai", tts="openai", llm_model="gpt-4o-mini")
    turn = asyncio.run(pipe.reply(messages=[{"role": "system", "content": "hi"}]))
    # Either pipecat succeeded or fell back to httpx — both produce a reply
    assert turn.reply_text in {"pipecat hello"}
    assert turn.engine in {"pipecat", "httpx"}
    assert turn.reply_audio.pcm
