"""Transport factory — voice-first for live platforms; text is CI/fallback."""

from __future__ import annotations

from wiretap.models import AgentTarget, TransportKind
from wiretap.transport.base import Inbound, Transport
from wiretap.transport.text import TextEchoTransport


def _wants_text_fallback(target: AgentTarget) -> bool:
    """Text Chat / stub only when explicitly requested."""
    if target.transport == TransportKind.TEXT:
        return True
    room = (target.room_url or "").lower().strip()
    return room in {"chat", "text", "vapi.chat"}


def build_transport(target: AgentTarget) -> Transport:
    kind = target.transport
    platform = (target.platform or "").lower().strip()

    # No platform → local stub (CI / dry-run)
    if not platform:
        return TextEchoTransport()

    if platform == "vapi":
        if _wants_text_fallback(target):
            from wiretap.transport.vapi import VapiTransport

            return VapiTransport()
        from wiretap.transport.vapi_ws import VapiWebSocketTransport

        return VapiWebSocketTransport()

    if platform == "retell":
        from wiretap.transport.retell import RetellTransport

        return RetellTransport()

    if platform == "elevenlabs":
        from wiretap.transport.elevenlabs import ElevenLabsTransport

        return ElevenLabsTransport()

    if platform == "livekit":
        from wiretap.transport.livekit_agents import LiveKitTransport

        return LiveKitTransport()

    if platform == "synthflow":
        from wiretap.transport.synthflow import SynthflowTransport

        return SynthflowTransport()

    if platform in {"bland", "bolna"}:
        raise NotImplementedError(
            f"{platform.title()} live phone dial is deferred. "
            f"Use `wiretap import {platform}` for suite/IR only, "
            "then a live Vapi/Retell/ElevenLabs/LiveKit/Synthflow agent."
        )

    if kind == TransportKind.TEXT:
        return TextEchoTransport()

    raise NotImplementedError(
        f"No transport for platform={target.platform!r} transport={kind.value!r}."
    )


__all__ = ["Inbound", "TextEchoTransport", "Transport", "build_transport"]
