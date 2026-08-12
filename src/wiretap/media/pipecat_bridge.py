"""Pipecat availability helper.

Pipecat is a core dependency. This module only answers “is it importable?”
for SpeechPipeline metadata. Flow orchestration lives in
``wiretap.caller.orchestrator`` (NodeConfig IR). Live TTS/STT for dials
lives in transports via ``wiretap.providers.factory``.
"""

from __future__ import annotations


def pipecat_available() -> bool:
    try:
        import pipecat  # noqa: F401

        return True
    except ImportError:
        return False


__all__ = ["pipecat_available"]
