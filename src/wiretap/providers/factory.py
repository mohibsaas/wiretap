"""OpenAI-compatible + vendor REST STT/TTS adapters.

Used by live transports (Vapi/Retell) for one-shot dial-in audio.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from wiretap.providers.audio_io import pcm_s16le_to_wav
from wiretap.providers.catalog import default_voice_for
from wiretap.providers.env import require_env
from wiretap.providers.http_retry import with_http_retries
from wiretap.providers.speech import AudioBuffer, SpeechToTextProvider, TextToSpeechProvider


# ---------------------------------------------------------------------------
# Shared OpenAI-compatible
# ---------------------------------------------------------------------------


class OpenAICompatTTS(TextToSpeechProvider):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        voice: str = "alloy",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.voice = voice

    async def synthesize(self, text: str) -> AudioBuffer:
        async def _once() -> AudioBuffer:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=60.0) as client:
                resp = await client.post(
                    "/audio/speech",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "voice": self.voice,
                        "input": text,
                        "response_format": "pcm",
                    },
                )
                resp.raise_for_status()
                return AudioBuffer(pcm=resp.content, sample_rate=24_000)

        return await with_http_retries(_once, label="tts")


class OpenAICompatSTT(SpeechToTextProvider):
    def __init__(self, *, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def transcribe(self, audio: AudioBuffer) -> str:
        wav = pcm_s16le_to_wav(audio.pcm, sample_rate=audio.sample_rate, channels=audio.channels)

        async def _once() -> str:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=60.0) as client:
                files = {"file": ("audio.wav", wav, "audio/wav")}
                data = {"model": self.model}
                resp = await client.post(
                    "/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files=files,
                    data=data,
                )
                resp.raise_for_status()
                payload = resp.json()
                return str(payload.get("text", ""))

        return await with_http_retries(_once, label="stt")


# ---------------------------------------------------------------------------
# Deepgram
# ---------------------------------------------------------------------------


class DeepgramSTT(SpeechToTextProvider):
    def __init__(self, *, api_key: str, model: str = "nova-2") -> None:
        self.api_key = api_key
        self.model = model

    async def transcribe(self, audio: AudioBuffer) -> str:
        wav = pcm_s16le_to_wav(audio.pcm, sample_rate=audio.sample_rate, channels=audio.channels)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.deepgram.com/v1/listen",
                params={"model": self.model, "smart_format": "true"},
                headers={
                    "Authorization": f"Token {self.api_key}",
                    "Content-Type": "audio/wav",
                },
                content=wav,
            )
            resp.raise_for_status()
            data = resp.json()
            try:
                return str(
                    data["results"]["channels"][0]["alternatives"][0].get("transcript", "")
                )
            except (KeyError, IndexError, TypeError):
                return ""


class DeepgramTTS(TextToSpeechProvider):
    def __init__(self, *, api_key: str, model: str = "aura-asteria-en") -> None:
        self.api_key = api_key
        self.model = model

    async def synthesize(self, text: str) -> AudioBuffer:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.deepgram.com/v1/speak",
                params={"model": self.model, "encoding": "linear16", "sample_rate": 24000},
                headers={
                    "Authorization": f"Token {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": text},
            )
            resp.raise_for_status()
            return AudioBuffer(pcm=resp.content, sample_rate=24_000)


# ---------------------------------------------------------------------------
# Cartesia / ElevenLabs / AssemblyAI / Gladia / Groq / LMNT / Rime / PlayHT
# ---------------------------------------------------------------------------


class CartesiaTTS(TextToSpeechProvider):
    def __init__(self, *, api_key: str, voice: str = "79a125e8-cd45-4c13-8a67-188112f4dd22") -> None:
        self.api_key = api_key
        self.voice = voice

    async def synthesize(self, text: str) -> AudioBuffer:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.cartesia.ai/tts/bytes",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Cartesia-Version": "2024-06-10",
                    "Content-Type": "application/json",
                },
                json={
                    "model_id": "sonic-english",
                    "transcript": text,
                    "voice": {"mode": "id", "id": self.voice},
                    "output_format": {
                        "container": "raw",
                        "encoding": "pcm_s16le",
                        "sample_rate": 24000,
                    },
                },
            )
            resp.raise_for_status()
            return AudioBuffer(pcm=resp.content, sample_rate=24_000)


class ElevenLabsTTS(TextToSpeechProvider):
    def __init__(
        self,
        *,
        api_key: str,
        voice: str = "21m00Tcm4TlvDq8ikWAM",
        # monolingual_v1 / multilingual_v1 were removed by ElevenLabs (HTTP 400).
        model: str = "eleven_flash_v2_5",
    ) -> None:
        self.api_key = api_key
        self.voice = voice
        self.model = _elevenlabs_tts_model(model)

    async def synthesize(self, text: str) -> AudioBuffer:
        async def _once() -> AudioBuffer:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice}",
                    params={"output_format": "pcm_24000"},
                    headers={
                        "xi-api-key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    json={"text": text, "model_id": self.model},
                )
                if resp.status_code in {408, 429, 500, 502, 503, 504}:
                    resp.raise_for_status()
                if resp.is_error:
                    raise RuntimeError(_elevenlabs_error_message(resp, what="TTS"))
                return AudioBuffer(pcm=resp.content, sample_rate=24_000)

        return await with_http_retries(_once, label="elevenlabs-tts")


def _elevenlabs_tts_model(model: str | None) -> str:
    """Map removed ElevenLabs TTS models to a supported default."""
    name = (model or "").strip() or "eleven_flash_v2_5"
    if name in {"eleven_monolingual_v1", "eleven_multilingual_v1"}:
        return "eleven_flash_v2_5"
    return name


def _elevenlabs_error_message(resp: httpx.Response, *, what: str) -> str:
    """Safe provider error for operators (no API keys / raw dumps)."""
    detail = ""
    try:
        payload = resp.json()
        raw = payload.get("detail") if isinstance(payload, dict) else None
        if isinstance(raw, dict):
            detail = str(raw.get("message") or raw.get("code") or "").strip()
        elif isinstance(raw, str):
            detail = raw.strip()
        elif isinstance(payload, dict):
            detail = str(payload.get("message") or "").strip()
    except Exception:
        detail = ""
    if detail:
        return f"ElevenLabs {what} failed ({resp.status_code}): {detail[:240]}"
    return f"ElevenLabs {what} failed ({resp.status_code})"


class ElevenLabsSTT(SpeechToTextProvider):
    """ElevenLabs Scribe batch STT (``scribe_v2``)."""

    def __init__(self, *, api_key: str, model: str = "scribe_v2") -> None:
        self.api_key = api_key
        self.model = model
        self._client = httpx.AsyncClient(timeout=120.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transcribe(self, audio: AudioBuffer) -> str:
        wav = pcm_s16le_to_wav(audio.pcm, sample_rate=audio.sample_rate, channels=audio.channels)

        async def _once() -> str:
            resp = await self._client.post(
                "https://api.elevenlabs.io/v1/speech-to-text",
                headers={"xi-api-key": self.api_key},
                files={"file": ("audio.wav", wav, "audio/wav")},
                data={"model_id": self.model},
            )
            if resp.status_code in {408, 429, 500, 502, 503, 504}:
                resp.raise_for_status()
            if resp.is_error:
                raise RuntimeError(_elevenlabs_error_message(resp, what="STT"))
            payload = resp.json()
            return str(payload.get("text") or "")

        return await with_http_retries(_once, label="elevenlabs-stt")


class AssemblyAISTT(SpeechToTextProvider):
    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    async def transcribe(self, audio: AudioBuffer) -> str:
        wav = pcm_s16le_to_wav(audio.pcm, sample_rate=audio.sample_rate, channels=audio.channels)
        headers = {"authorization": self.api_key}
        async with httpx.AsyncClient(timeout=120.0) as client:
            up = await client.post(
                "https://api.assemblyai.com/v2/upload",
                headers=headers,
                content=wav,
            )
            up.raise_for_status()
            upload_url = up.json().get("upload_url")
            if not upload_url:
                raise RuntimeError("AssemblyAI upload missing upload_url")
            create = await client.post(
                "https://api.assemblyai.com/v2/transcript",
                headers={**headers, "content-type": "application/json"},
                json={"audio_url": upload_url},
            )
            create.raise_for_status()
            tid = create.json().get("id")
            if not tid:
                raise RuntimeError("AssemblyAI transcript missing id")
            for _ in range(60):
                st = await client.get(
                    f"https://api.assemblyai.com/v2/transcript/{tid}",
                    headers=headers,
                )
                st.raise_for_status()
                body = st.json()
                status = body.get("status")
                if status == "completed":
                    return str(body.get("text") or "")
                if status == "error":
                    raise RuntimeError(f"AssemblyAI error: {body.get('error')}")
                import asyncio

                await asyncio.sleep(1.0)
        raise TimeoutError("AssemblyAI transcription timed out")


class GladiaSTT(SpeechToTextProvider):
    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    async def transcribe(self, audio: AudioBuffer) -> str:
        wav = pcm_s16le_to_wav(audio.pcm, sample_rate=audio.sample_rate, channels=audio.channels)
        headers = {"x-gladia-key": self.api_key}
        async with httpx.AsyncClient(timeout=120.0) as client:
            up = await client.post(
                "https://api.gladia.io/v2/upload",
                headers=headers,
                files={"audio": ("audio.wav", wav, "audio/wav")},
            )
            up.raise_for_status()
            audio_url = up.json().get("audio_url")
            if not audio_url:
                raise RuntimeError("Gladia upload missing audio_url")
            job = await client.post(
                "https://api.gladia.io/v2/pre-recorded",
                headers={**headers, "Content-Type": "application/json"},
                json={"audio_url": audio_url},
            )
            job.raise_for_status()
            result_url = job.json().get("result_url")
            if not result_url:
                # sync-ish payload
                return _gladia_text(job.json())
            for _ in range(60):
                st = await client.get(result_url, headers=headers)
                st.raise_for_status()
                body = st.json()
                status = (body.get("status") or "").lower()
                if status in {"done", "completed", "success"}:
                    return _gladia_text(body)
                if status in {"error", "failed"}:
                    raise RuntimeError(f"Gladia error: {body}")
                import asyncio

                await asyncio.sleep(1.0)
        raise TimeoutError("Gladia transcription timed out")


def _gladia_text(body: dict[str, Any]) -> str:
    result = body.get("result") or body
    transcription = result.get("transcription") or {}
    if isinstance(transcription, dict) and transcription.get("full_transcript"):
        return str(transcription["full_transcript"])
    return str(result.get("prediction") or result.get("text") or "")


class GroqSTT(SpeechToTextProvider):
    def __init__(self, *, api_key: str, model: str = "whisper-large-v3") -> None:
        self._inner = OpenAICompatSTT(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
            model=model,
        )

    async def transcribe(self, audio: AudioBuffer) -> str:
        return await self._inner.transcribe(audio)


class LmntTTS(TextToSpeechProvider):
    def __init__(self, *, api_key: str, voice: str = "lily") -> None:
        self.api_key = api_key
        self.voice = voice

    async def synthesize(self, text: str) -> AudioBuffer:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.lmnt.com/v1/ai/speech",
                headers={"X-API-Key": self.api_key},
                json={"text": text, "voice": self.voice, "format": "wav"},
            )
            resp.raise_for_status()
            from wiretap.providers.audio_io import wav_to_pcm_s16le

            pcm, rate, _ = wav_to_pcm_s16le(resp.content)
            return AudioBuffer(pcm=pcm, sample_rate=rate)


class RimeTTS(TextToSpeechProvider):
    def __init__(self, *, api_key: str, voice: str = "luna") -> None:
        self.api_key = api_key
        self.voice = voice

    async def synthesize(self, text: str) -> AudioBuffer:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://users.rime.ai/v1/rime-tts",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "audio/pcm",
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "speaker": self.voice,
                    "modelId": "mist",
                    "samplingRate": 24000,
                },
            )
            resp.raise_for_status()
            return AudioBuffer(pcm=resp.content, sample_rate=24_000)


class PlayHTTTS(TextToSpeechProvider):
    def __init__(self, *, api_key: str, user_id: str, voice: str) -> None:
        self.api_key = api_key
        self.user_id = user_id
        self.voice = voice

    async def synthesize(self, text: str) -> AudioBuffer:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.play.ht/api/v2/tts/stream",
                headers={
                    "AUTHORIZATION": self.api_key,
                    "X-USER-ID": self.user_id,
                    "Accept": "audio/wav",
                    "Content-Type": "application/json",
                },
                json={"text": text, "voice": self.voice, "output_format": "wav"},
            )
            resp.raise_for_status()
            from wiretap.providers.audio_io import wav_to_pcm_s16le

            pcm, rate, _ = wav_to_pcm_s16le(resp.content)
            return AudioBuffer(pcm=pcm, sample_rate=rate)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_tts(provider: str, voice: str | None = None) -> TextToSpeechProvider:
    name = (provider or "pyai").lower().strip()
    voice = (voice or "").strip() or default_voice_for(name)

    if name == "pyai":
        return OpenAICompatTTS(
            api_key=require_env("PYAI_API_KEY"),
            base_url="https://api.pyai.com/v1",
            model="pyai-voice",
            voice=voice,
        )
    if name in {"openai", "openai_tts"}:
        return OpenAICompatTTS(
            api_key=require_env("OPENAI_API_KEY"),
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini-tts",
            voice=voice,
        )
    if name == "deepgram":
        return DeepgramTTS(
            api_key=require_env("DEEPGRAM_API_KEY"),
            model=voice or default_voice_for("deepgram"),
        )
    if name == "cartesia":
        return CartesiaTTS(
            api_key=require_env("CARTESIA_API_KEY"),
            voice=voice,
        )
    if name == "elevenlabs":
        return ElevenLabsTTS(
            api_key=require_env("ELEVENLABS_API_KEY"),
            voice=voice,
        )
    if name == "lmnt":
        return LmntTTS(api_key=require_env("LMNT_API_KEY"), voice=voice)
    if name == "rime":
        return RimeTTS(api_key=require_env("RIME_API_KEY"), voice=voice)
    if name == "playht":
        user = os.environ.get("PLAYHT_USER_ID", "").strip()
        if not user:
            raise RuntimeError("PLAYHT_USER_ID required for PlayHT TTS")
        return PlayHTTTS(
            api_key=require_env("PLAYHT_API_KEY"),
            user_id=user,
            voice=voice,
        )
    raise ValueError(
        f"Unknown TTS provider: {provider!r}. "
        "Use pyai, openai, deepgram, cartesia, elevenlabs, lmnt, rime, or playht."
    )


def build_stt(provider: str) -> SpeechToTextProvider:
    name = (provider or "pyai").lower().strip()

    if name == "pyai":
        return OpenAICompatSTT(
            api_key=require_env("PYAI_API_KEY"),
            base_url="https://api.pyai.com/v1",
            model="pyai-hear",
        )
    if name in {"openai", "whisper"}:
        return OpenAICompatSTT(
            api_key=require_env("OPENAI_API_KEY"),
            base_url="https://api.openai.com/v1",
            model="whisper-1",
        )
    if name == "deepgram":
        return DeepgramSTT(api_key=require_env("DEEPGRAM_API_KEY"))
    if name == "elevenlabs":
        return ElevenLabsSTT(api_key=require_env("ELEVENLABS_API_KEY"))
    if name == "assemblyai":
        return AssemblyAISTT(api_key=require_env("ASSEMBLYAI_API_KEY"))
    if name == "gladia":
        return GladiaSTT(api_key=require_env("GLADIA_API_KEY"))
    if name == "groq":
        return GroqSTT(api_key=require_env("GROQ_API_KEY"))
    raise ValueError(
        f"Unknown STT provider: {provider!r}. "
        "Use pyai, openai, deepgram, elevenlabs, assemblyai, gladia, or groq."
    )


__all__ = ["build_stt", "build_tts"]
