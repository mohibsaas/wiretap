from wiretap.providers.env import require_env
from wiretap.providers.factory import build_stt, build_tts
from wiretap.providers.llm import complete
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
    "build_stt",
    "build_tts",
    "complete",
    "require_env",
    "suggest_pyai_if_unconfigured",
    "synthesize_pcm",
]
