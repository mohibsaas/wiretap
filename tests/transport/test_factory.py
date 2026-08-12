"""Transport factory selection — voice-first."""

from wiretap.models import AgentTarget, TransportKind
from wiretap.transport import build_transport
from wiretap.transport.text import TextEchoTransport
from wiretap.transport.vapi import VapiTransport
from wiretap.transport.vapi_ws import VapiWebSocketTransport


def test_text_stub_no_platform() -> None:
    t = build_transport(AgentTarget(transport=TransportKind.TEXT))
    assert isinstance(t, TextEchoTransport)


def test_vapi_defaults_to_voice_ws() -> None:
    t = build_transport(
        AgentTarget(transport=TransportKind.WEBRTC, platform="vapi", agent_id="asst_x")
    )
    assert isinstance(t, VapiWebSocketTransport)


def test_vapi_text_chat_opt_in() -> None:
    t = build_transport(
        AgentTarget(
            transport=TransportKind.TEXT,
            platform="vapi",
            agent_id="asst_x",
            room_url="chat",
        )
    )
    assert isinstance(t, VapiTransport)


def test_vapi_chat_via_room_url() -> None:
    t = build_transport(
        AgentTarget(
            transport=TransportKind.WEBRTC,
            platform="vapi",
            agent_id="asst_x",
            room_url="text",
        )
    )
    assert isinstance(t, VapiTransport)
