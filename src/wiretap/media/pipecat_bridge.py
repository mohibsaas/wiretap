"""Optional Pipecat integration helpers.

Core speech uses HTTP adapters in ``wiretap.providers.factory``. When
``pipecat-ai`` is installed, ``SpeechPipeline`` runs STT→LLM→TTS through a
Pipecat ``Pipeline`` / ``PipelineTask``.
"""

from __future__ import annotations

from typing import Any


def pipecat_available() -> bool:
    try:
        import pipecat  # noqa: F401

        return True
    except ImportError:
        return False


def describe_pipeline(*, stt: str, tts: str, llm_model: str) -> dict[str, Any]:
    """Return a declarative pipeline map (and whether Pipecat is importable)."""
    from wiretap.media.pipeline import build_speech_pipeline

    pipe = build_speech_pipeline(stt=stt, tts=tts, llm_model=llm_model)
    desc = pipe.describe()
    desc["flows"] = "use scenario.flow_phases; pipecat.flows available when installed"
    return desc


def try_import_flows():
    """Import pipecat.flows if present (Pipecat ≥1.5)."""
    if not pipecat_available():
        return None
    try:
        from pipecat import flows

        return flows
    except ImportError:
        return None


__all__ = ["describe_pipeline", "pipecat_available", "try_import_flows"]
