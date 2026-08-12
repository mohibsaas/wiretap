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
        # Primary: live voice over Vapi WebSocket PCM
        from wiretap.transport.vapi_ws import VapiWebSocketTransport

        return VapiWebSocketTransport()

    if platform == "retell":
        # Primary: LiveKit web-call (real voice)
        from wiretap.transport.retell import RetellTransport

        return RetellTransport()

    if platform == "bland":
        raise NotImplementedError(
            "Bland live phone dial is deferred. "
            "Use `wiretap import bland` for suite/IR only, then a live Vapi/Retell agent."
        )

    if kind == TransportKind.TEXT:
        return TextEchoTransport()

    raise NotImplementedError(
        f"No transport for platform={target.platform!r} transport={kind.value!r}."
    )


__all__ = ["Inbound", "TextEchoTransport", "Transport", "build_transport"]
