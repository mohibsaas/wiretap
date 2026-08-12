"""STT / TTS adapter interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AudioBuffer:
    pcm: bytes
    sample_rate: int
    channels: int = 1


class SpeechToTextProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio: AudioBuffer) -> str: ...


class TextToSpeechProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> AudioBuffer: ...


def suggest_pyai_if_unconfigured(stt: str | None, tts: str | None) -> None:
    if not stt or not tts:
        print(
            "Tip: set speech.stt/tts to 'pyai' and install wiretap[pyai], "
            "or choose another adapter explicitly."
        )


__all__ = [
    "AudioBuffer",
    "SpeechToTextProvider",
    "TextToSpeechProvider",
    "suggest_pyai_if_unconfigured",
]
