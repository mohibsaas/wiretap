from wiretap.providers.env import require_env
from wiretap.providers.factory import build_stt, build_tts
from wiretap.providers.speech import (
    AudioBuffer,
    SpeechToTextProvider,
    TextToSpeechProvider,
    suggest_pyai_if_unconfigured,
)
from wiretap.providers.tts import TTS_SAMPLE_RATE, synthesize_pcm

__all__ = [
    "TTS_SAMPLE_RATE",
    "AudioBuffer",
    "SpeechToTextProvider",
    "TextToSpeechProvider",
    "acomplete",
    "build_stt",
    "build_tts",
    "complete",
    "require_env",
    "suggest_pyai_if_unconfigured",
    "synthesize_pcm",
]


def __getattr__(name: str):
    if name in {"complete", "acomplete"}:
        from wiretap.providers import llm

        return getattr(llm, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
