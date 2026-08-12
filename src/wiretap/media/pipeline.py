"""Speech pipeline: STT → LLM → TTS for the wiretap test agent.

When ``pipecat-ai`` is installed, one-shot turns run through a Pipecat
``Pipeline`` of linked ``FrameProcessor`` stages (direct mode). Otherwise the
same factory + LiteLLM path is used (core works without Pipecat).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from wiretap.providers.factory import build_stt, build_tts
from wiretap.providers.llm import complete
from wiretap.providers.speech import AudioBuffer


@dataclass
class PipelineTurn:
    """One STT→LLM→TTS cycle."""

    transcript: str
    reply_text: str
    reply_audio: AudioBuffer
    engine: str


@dataclass
class SpeechPipeline:
    """Test-agent media stack bound to suite speech + model slots."""

    stt: str = "pyai"
    tts: str = "pyai"
    voice: str | None = "alloy"
    llm_model: str = "gpt-4o-mini"
    temperature: float = 0.4

    def describe(self) -> dict[str, Any]:
        from wiretap.media.pipecat_bridge import pipecat_available

        return {
            "engine": "pipecat" if pipecat_available() else "httpx",
            "pipecat_available": pipecat_available(),
            "stages": [
                {"type": "stt", "provider": self.stt},
                {"type": "llm", "model": self.llm_model},
                {"type": "tts", "provider": self.tts},
            ],
        }

    async def transcribe(self, audio: AudioBuffer) -> str:
        return await build_stt(self.stt).transcribe(audio)

    async def synthesize(self, text: str) -> AudioBuffer:
        return await build_tts(self.tts, self.voice).synthesize(text)

    async def reply(
        self,
        *,
        messages: list[dict[str, str]],
        audio: AudioBuffer | None = None,
    ) -> PipelineTurn:
        """Optional STT on ``audio``, then LLM reply, then TTS."""
        from wiretap.media.pipecat_bridge import pipecat_available

        transcript = ""
        if audio is not None and audio.pcm:
            transcript = (await self.transcribe(audio)).strip()
            if transcript:
                messages = [*messages, {"role": "user", "content": transcript}]

        if pipecat_available():
            try:
                return await asyncio.wait_for(
                    self._run_pipecat(messages=messages, transcript=transcript),
                    timeout=30.0,
                )
            except Exception:
                return await self._run_httpx(messages=messages, transcript=transcript)
        return await self._run_httpx(messages=messages, transcript=transcript)

    async def _run_httpx(
        self,
        *,
        messages: list[dict[str, str]],
        transcript: str,
    ) -> PipelineTurn:
        reply_text = complete(
            model=self.llm_model,
            messages=messages,
            temperature=self.temperature,
        )
        audio = await self.synthesize(reply_text)
        return PipelineTurn(
            transcript=transcript,
            reply_text=reply_text,
            reply_audio=audio,
            engine="httpx",
        )

    async def _run_pipecat(
        self,
        *,
        messages: list[dict[str, str]],
        transcript: str,
    ) -> PipelineTurn:
        """Drive LLM→TTS through linked Pipecat FrameProcessors (direct mode).

        Uses ``enable_direct_mode`` + ``link()`` so frames process inline without
        a long-lived PipelineWorker/event loop (avoids hangs in one-shot turns).
        """
        from pipecat.frames.frames import EndFrame, Frame, TextFrame
        from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

        tts_name, voice, model, temp = self.tts, self.voice, self.llm_model, self.temperature
        collected: dict[str, Any] = {}

        class LlmStage(FrameProcessor):
            def __init__(self) -> None:
                super().__init__(enable_direct_mode=True)

            async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
                await super().process_frame(frame, direction)
                if isinstance(frame, TextFrame):
                    text = complete(model=model, messages=messages, temperature=temp)
                    collected["reply"] = text
                    await self.push_frame(TextFrame(text=text), direction)
                    return
                await self.push_frame(frame, direction)

        class TtsStage(FrameProcessor):
            def __init__(self) -> None:
                super().__init__(enable_direct_mode=True)

            async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
                await super().process_frame(frame, direction)
                if isinstance(frame, TextFrame) and frame.text:
                    collected["audio"] = await build_tts(tts_name, voice).synthesize(frame.text)
                await self.push_frame(frame, direction)

        llm = LlmStage()
        tts = TtsStage()
        llm.link(tts)

        await llm.queue_frame(TextFrame(text="__kick__"), FrameDirection.DOWNSTREAM)
        await llm.queue_frame(EndFrame(), FrameDirection.DOWNSTREAM)

        reply_text = str(collected.get("reply") or "")
        audio = collected.get("audio")
        if not reply_text or not isinstance(audio, AudioBuffer):
            raise RuntimeError("Pipecat pipeline did not produce reply audio")
        return PipelineTurn(
            transcript=transcript,
            reply_text=reply_text,
            reply_audio=audio,
            engine="pipecat",
        )


def build_speech_pipeline(
    *,
    stt: str = "pyai",
    tts: str = "pyai",
    voice: str | None = "alloy",
    llm_model: str = "gpt-4o-mini",
    temperature: float = 0.4,
) -> SpeechPipeline:
    return SpeechPipeline(
        stt=stt,
        tts=tts,
        voice=voice,
        llm_model=llm_model,
        temperature=temperature,
    )


__all__ = [
    "PipelineTurn",
    "SpeechPipeline",
    "build_speech_pipeline",
]
