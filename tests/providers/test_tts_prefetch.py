"""TTS prefetch / cache helpers."""

from __future__ import annotations

import asyncio

from wiretap.providers import tts as tts_mod


def test_prefetch_then_synthesize_hits_cache(monkeypatch) -> None:
    calls = {"n": 0}

    class _FakeTTS:
        async def synthesize(self, text: str):  # noqa: ANN001
            calls["n"] += 1
            await asyncio.sleep(0.05)
            from wiretap.providers.speech import AudioBuffer

            return AudioBuffer(pcm=f"pcm:{text}".encode(), sample_rate=24_000)

    monkeypatch.setattr(tts_mod, "build_tts", lambda *_a, **_k: _FakeTTS())
    tts_mod.clear_tts_cache()

    async def _run() -> None:
        tts_mod.prefetch_pcm("Hello there", voice="v", provider="elevenlabs")
        await asyncio.sleep(0.02)
        pcm = await tts_mod.synthesize_pcm(
            "Hello there", voice="v", provider="elevenlabs"
        )
        assert pcm == b"pcm:Hello there"
        assert calls["n"] == 1
        pcm2 = await tts_mod.synthesize_pcm(
            "Hello there", voice="v", provider="elevenlabs"
        )
        assert pcm2 == pcm
        assert calls["n"] == 1

    asyncio.run(_run())
    tts_mod.clear_tts_cache()
