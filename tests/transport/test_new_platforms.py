"""Transport factory selection — new platforms."""

from wiretap.models import AgentTarget, TransportKind
from wiretap.transport import build_transport
from wiretap.transport.elevenlabs import ElevenLabsTransport
from wiretap.transport.livekit_agents import LiveKitTransport, mint_livekit_jwt
from wiretap.transport.synthflow import SynthflowTransport


def test_elevenlabs_factory() -> None:
    t = build_transport(
        AgentTarget(transport=TransportKind.WEBRTC, platform="elevenlabs", agent_id="ag_x")
    )
    assert isinstance(t, ElevenLabsTransport)


def test_livekit_factory() -> None:
    t = build_transport(
        AgentTarget(
            transport=TransportKind.WEBRTC,
            platform="livekit",
            agent_id="room-1",
            room_url="wss://example.livekit.cloud",
        )
    )
    assert isinstance(t, LiveKitTransport)


def test_synthflow_factory() -> None:
    t = build_transport(
        AgentTarget(transport=TransportKind.WEBRTC, platform="synthflow", agent_id="model-1")
    )
    assert isinstance(t, SynthflowTransport)


def test_bolna_deferred() -> None:
    try:
        build_transport(
            AgentTarget(transport=TransportKind.PSTN, platform="bolna", agent_id="a1")
        )
        raise AssertionError("expected NotImplementedError")
    except NotImplementedError as exc:
        assert "Bolna" in str(exc) or "bolna" in str(exc).lower()


def test_mint_livekit_jwt_shape() -> None:
    token = mint_livekit_jwt(
        api_key="APIkey",
        api_secret="secret",
        identity="wiretap",
        room="demo",
        ttl_sec=60,
    )
    parts = token.split(".")
    assert len(parts) == 3
    assert all(parts)
