"""PSTN transport — call setup, audio bridging and post-call id resolution.

Pure unit tests: the SIP layer is a fake implementing the seam, and Twilio /
platform HTTP is either injected or stubbed. Nothing here touches the network.
"""

from __future__ import annotations

import array
import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from wiretap.models import AgentTarget, TransportKind
from wiretap.providers.speech import AudioBuffer
from wiretap.services.twilio_pstn import SipEndpoint
from wiretap.transport import build_transport
from wiretap.transport import twilio_pstn as mod
from wiretap.transport.platform_lookup import resolve_platform_call_id
from wiretap.transport.pstn_audio import SILENCE_BYTE, STT_SAMPLE_RATE, pstn_to_pcm16
from wiretap.transport.sip_client import SipClient
from wiretap.transport.twilio_pstn import TwilioPstnTransport

ENDPOINT = SipEndpoint(
    domain="wiretap-abc.sip.twilio.com", username="wiretap", password="Secret123456"
)
CALLER = "+14155550199"
AGENT_NUMBER = "+14155550123"


def speech(length: int = 800) -> bytes:
    """8-bit unsigned linear audio loud enough to pass the energy gate."""
    return bytes(0x80 + (60 if i % 2 else -60) for i in range(length))


def silence(length: int = 800) -> bytes:
    return b"\x80" * length


class FakeSip(SipClient):
    def __init__(self, frames: list[bytes] | None = None, *, answers: bool = True) -> None:
        self.frames = list(frames or [])
        self.answers = answers
        self.written = bytearray()
        self.started = False
        self.stopped = False
        self.active = True
        # Stay active while frames remain unless a test says otherwise.
        self.deactivate_when_drained = True

    def start(self) -> None:
        self.started = True

    def wait_for_call(self, timeout: float) -> bool:
        return self.answers

    def is_active(self) -> bool:
        if not self.frames and self.deactivate_when_drained:
            self.active = False
        return self.active

    def read_audio(self, length: int = 160) -> bytes:
        return self.frames.pop(0) if self.frames else b""

    def write_audio(self, payload: bytes) -> None:
        self.written.extend(payload)

    def stop(self) -> None:
        self.stopped = True
        self.active = False


class FakeStt:
    def __init__(self, transcripts: list[str]) -> None:
        self.transcripts = list(transcripts)
        self.received: list[AudioBuffer] = []

    async def transcribe(self, audio: AudioBuffer) -> str:
        self.received.append(audio)
        return self.transcripts.pop(0) if self.transcripts else ""


class FakeTts:
    def __init__(self, sample_rate: int = 24_000) -> None:
        self.sample_rate = sample_rate
        self.spoken: list[str] = []

    async def synthesize(self, text: str) -> AudioBuffer:
        self.spoken.append(text)
        samples = array.array("h", [12_000, -12_000] * 1_200)
        return AudioBuffer(pcm=samples.tobytes(), sample_rate=self.sample_rate)


@pytest.fixture()
def wired(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub every outbound Twilio call the transport makes during connect."""
    placed: dict[str, Any] = {}
    hungup: list[str] = []

    def place(**kwargs: Any) -> str:
        placed.update(kwargs)
        return "CA123"

    monkeypatch.setattr(mod, "twilio_client", lambda: object())
    monkeypatch.setattr(mod, "ensure_sip_endpoint", lambda client: ENDPOINT)
    monkeypatch.setattr(mod, "place_bridge_call", place)
    monkeypatch.setattr(mod, "resolve_from_number", lambda: CALLER)
    monkeypatch.setattr(mod, "hangup_call", lambda sid: hungup.append(sid))
    return {"placed": placed, "hungup": hungup}


def target(**overrides: Any) -> AgentTarget:
    fields: dict[str, Any] = {
        "transport": TransportKind.PSTN,
        "platform": "retell",
        "agent_id": "agent_1",
        "phone_number": AGENT_NUMBER,
    }
    fields.update(overrides)
    return AgentTarget(**fields)


def test_factory_returns_the_pstn_transport_for_any_platform() -> None:
    assert isinstance(build_transport(target()), TwilioPstnTransport)
    assert isinstance(build_transport(target(platform="vapi")), TwilioPstnTransport)


def test_factory_still_routes_non_pstn_transports_by_platform() -> None:
    from wiretap.transport.vapi_ws import VapiWebSocketTransport

    built = build_transport(
        AgentTarget(transport=TransportKind.WEBRTC, platform="vapi", agent_id="a")
    )

    assert isinstance(built, VapiWebSocketTransport)


def test_connect_requires_a_phone_number(wired: dict[str, Any]) -> None:
    transport = TwilioPstnTransport(sip_factory=lambda ep: FakeSip())

    with pytest.raises(ValueError, match="E.164"):
        asyncio.run(transport.connect(target(phone_number=None)))


def test_connect_rejects_an_unparsable_phone_number(wired: dict[str, Any]) -> None:
    transport = TwilioPstnTransport(sip_factory=lambda ep: FakeSip())

    with pytest.raises(ValueError, match="agent phone number"):
        asyncio.run(transport.connect(target(phone_number="555-0123")))


def test_connect_without_a_caller_number_explains_how_to_set_one(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "resolve_from_number", lambda: None)
    transport = TwilioPstnTransport(sip_factory=lambda ep: FakeSip())

    with pytest.raises(RuntimeError, match="TWILIO_FROM_NUMBER"):
        asyncio.run(transport.connect(target()))


def test_connect_registers_then_bridges_to_the_agent(wired: dict[str, Any]) -> None:
    sip = FakeSip()
    transport = TwilioPstnTransport(sip_factory=lambda ep: sip)

    asyncio.run(transport.connect(target()))

    assert sip.started
    assert wired["placed"] == {
        "to_number": AGENT_NUMBER,
        "from_number": CALLER,
        "sip_uri": ENDPOINT.uri,
        "client": wired["placed"]["client"],
    }
    assert transport._call_sid == "CA123"


def test_ready_marker_is_queued_so_the_agent_may_speak_first(
    wired: dict[str, Any],
) -> None:
    transport = TwilioPstnTransport(sip_factory=lambda ep: FakeSip())

    async def scenario() -> Any:
        await transport.connect(target())
        return await transport.receive()

    inbound = asyncio.run(scenario())

    assert inbound.text == ""
    assert not inbound.hung_up


def test_an_unbridged_call_fails_loudly_and_tears_down(
    wired: dict[str, Any],
) -> None:
    sip = FakeSip(answers=False)
    transport = TwilioPstnTransport(sip_factory=lambda ep: sip)

    with pytest.raises(RuntimeError, match="never bridged"):
        asyncio.run(transport.connect(target()))

    assert sip.stopped
    assert wired["hungup"] == ["CA123"]


def test_agent_speech_is_transcribed_into_a_turn(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    stt = FakeStt(["Thanks for calling Acme, how can I help?"])
    monkeypatch.setattr(mod, "build_stt", lambda name: stt)
    sip = FakeSip([speech(), speech()])
    transport = TwilioPstnTransport(sip_factory=lambda ep: sip)

    async def scenario() -> list[Any]:
        await transport.connect(target())
        await transport.receive()  # ready marker
        return [await transport.receive(), await transport.receive()]

    turn, ended = asyncio.run(scenario())

    assert turn.text == "Thanks for calling Acme, how can I help?"
    assert ended.hung_up
    assert stt.received[0].sample_rate == STT_SAMPLE_RATE


def test_line_noise_never_becomes_an_agent_turn(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ringback transcribes to junk; a bogus turn would mislead the judge."""
    stt = FakeStt(["."])
    monkeypatch.setattr(mod, "build_stt", lambda name: stt)
    sip = FakeSip([speech(), speech()])
    transport = TwilioPstnTransport(sip_factory=lambda ep: sip)

    async def scenario() -> Any:
        await transport.connect(target())
        await transport.receive()
        return await transport.receive()

    assert asyncio.run(scenario()).hung_up


def test_pure_silence_never_reaches_stt(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    stt = FakeStt(["should not be called"])
    monkeypatch.setattr(mod, "build_stt", lambda name: stt)
    sip = FakeSip([silence(), silence(), silence()])
    transport = TwilioPstnTransport(sip_factory=lambda ep: sip)

    async def scenario() -> Any:
        await transport.connect(target())
        await transport.receive()
        return await transport.receive()

    assert asyncio.run(scenario()).hung_up
    assert stt.received == []


def test_a_pause_splits_the_stream_into_one_utterance(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "SILENCE_FLUSH_SECONDS", 0.05)
    monkeypatch.setattr(mod, "READ_INTERVAL_SECONDS", 0.01)
    stt = FakeStt(["first utterance"])
    monkeypatch.setattr(mod, "build_stt", lambda name: stt)
    sip = FakeSip([speech(), speech()] + [silence()] * 40)
    sip.deactivate_when_drained = False
    transport = TwilioPstnTransport(sip_factory=lambda ep: sip)

    async def scenario() -> Any:
        await transport.connect(target())
        await transport.receive()
        inbound = await transport.receive()
        await transport.hangup()
        return inbound

    inbound = asyncio.run(scenario())

    assert inbound.text == "first utterance"
    assert len(stt.received) == 1


def test_send_text_writes_downsampled_telephony_audio(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    tts = FakeTts(sample_rate=24_000)
    monkeypatch.setattr(mod, "build_tts", lambda name, voice: tts)
    sip = FakeSip()
    sip.deactivate_when_drained = False
    transport = TwilioPstnTransport(sip_factory=lambda ep: sip)

    async def scenario() -> None:
        await transport.connect(target())
        await transport.send_text("Hi, I need to reschedule.")

    asyncio.run(scenario())

    assert tts.spoken == ["Hi, I need to reschedule."]
    # 2400 samples at 24 kHz → 800 bytes at 8 kHz, one byte per sample.
    assert len(sip.written) == 800


def test_send_text_before_connect_is_a_programming_error() -> None:
    with pytest.raises(RuntimeError, match="not connected"):
        asyncio.run(TwilioPstnTransport().send_text("hello"))


def test_receive_times_out_into_a_hangup(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "RECEIVE_TIMEOUT_SECONDS", 0.05)
    sip = FakeSip()
    sip.deactivate_when_drained = False
    transport = TwilioPstnTransport(sip_factory=lambda ep: sip)

    async def scenario() -> Any:
        await transport.connect(target())
        await transport.receive()
        return await transport.receive()

    assert asyncio.run(scenario()).hung_up


def test_hangup_ends_both_legs(wired: dict[str, Any]) -> None:
    sip = FakeSip()
    transport = TwilioPstnTransport(sip_factory=lambda ep: sip)

    async def scenario() -> None:
        await transport.connect(target())
        await transport.hangup()

    asyncio.run(scenario())

    assert sip.stopped
    assert wired["hungup"] == ["CA123"]


def test_call_ref_is_none_until_the_platform_id_is_resolved(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unresolvable id must report unsupported capture, not fail the run."""
    monkeypatch.setenv("RETELL_API_KEY", "key")
    monkeypatch.setattr(mod, "resolve_platform_call_id", _returns(None))
    transport = TwilioPstnTransport(sip_factory=lambda ep: FakeSip())

    async def scenario() -> None:
        await transport.connect(target())
        assert transport.call_ref() is None
        await transport.hangup()

    asyncio.run(scenario())

    assert transport.call_ref() is None


def test_hangup_resolves_the_platform_call_for_tool_capture(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RETELL_API_KEY", "key")
    seen: dict[str, Any] = {}

    async def resolve(**kwargs: Any) -> str:
        seen.update(kwargs)
        return "call_abc"

    monkeypatch.setattr(mod, "resolve_platform_call_id", resolve)
    transport = TwilioPstnTransport(sip_factory=lambda ep: FakeSip())

    async def scenario() -> None:
        await transport.connect(target())
        await transport.hangup()

    asyncio.run(scenario())

    ref = transport.call_ref()
    assert ref is not None
    assert ref.platform == "retell"
    assert ref.call_id == "call_abc"
    assert seen["agent_id"] == "agent_1"
    assert seen["phone_number"] == AGENT_NUMBER


def test_a_missing_platform_key_skips_resolution_silently(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("RETELL_API_KEY", raising=False)
    monkeypatch.setattr("wiretap.services.secrets.load_dotenv", lambda *a, **k: None)

    async def explode(**kwargs: Any) -> str:
        raise AssertionError("must not call the platform without a key")

    monkeypatch.setattr(mod, "resolve_platform_call_id", explode)
    transport = TwilioPstnTransport(sip_factory=lambda ep: FakeSip())

    async def scenario() -> None:
        await transport.connect(target())
        await transport.hangup()

    asyncio.run(scenario())

    assert transport.call_ref() is None


def test_recorded_audio_is_the_mixed_call(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "build_stt", lambda name: FakeStt([]))
    monkeypatch.setattr(mod, "build_tts", lambda name, voice: FakeTts(16_000))
    captured: list[tuple[int, int]] = []

    class Recorder:
        def add(self, pcm: bytes, *, sample_rate: int) -> None:
            captured.append((len(pcm), sample_rate))

    sip = FakeSip([speech()])
    sip.deactivate_when_drained = False
    transport = TwilioPstnTransport(sip_factory=lambda ep: sip)
    transport.attach_recorder(Recorder())

    async def scenario() -> None:
        await transport.connect(target())
        await asyncio.sleep(0.15)
        await transport.send_text("hello")

    asyncio.run(scenario())

    assert captured
    assert {rate for _, rate in captured} == {STT_SAMPLE_RATE}
    assert (len(pstn_to_pcm16(speech())), STT_SAMPLE_RATE) in captured


# --- post-call platform lookup -------------------------------------------------

DIALED_AT = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def _returns(value: Any) -> Any:
    async def _inner(**kwargs: Any) -> Any:
        return value

    return _inner


def _mock_client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_retell_lookup_picks_the_call_we_just_dialed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/list-calls"
        return httpx.Response(
            200,
            json=[
                {
                    "call_id": "stale",
                    "start_timestamp": DIALED_AT.timestamp() * 1000 - 3_600_000,
                    "to_number": AGENT_NUMBER,
                },
                {
                    "call_id": "ours",
                    "start_timestamp": DIALED_AT.timestamp() * 1000 + 2_000,
                    "to_number": AGENT_NUMBER,
                },
            ],
        )

    async def scenario() -> str | None:
        async with _mock_client(handler) as client:
            return await resolve_platform_call_id(
                platform="retell",
                agent_id="agent_1",
                api_key="key",
                dialed_at=DIALED_AT,
                phone_number=AGENT_NUMBER,
                client=client,
            )

    assert asyncio.run(scenario()) == "ours"


def test_retell_lookup_ignores_calls_from_before_the_dial() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "call_id": "yesterday",
                    "start_timestamp": DIALED_AT.timestamp() * 1000 - 86_400_000,
                    "to_number": AGENT_NUMBER,
                }
            ],
        )

    async def scenario() -> str | None:
        async with _mock_client(handler) as client:
            return await resolve_platform_call_id(
                platform="retell",
                agent_id="agent_1",
                api_key="key",
                dialed_at=DIALED_AT,
                client=client,
            )

    assert asyncio.run(scenario()) is None


def test_vapi_lookup_uses_the_newest_call_for_the_assistant() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[{"id": "call_v1"}, {"id": "call_v0"}])

    async def scenario() -> str | None:
        async with _mock_client(handler) as client:
            return await resolve_platform_call_id(
                platform="vapi",
                agent_id="asst_1",
                api_key="key",
                dialed_at=DIALED_AT,
                client=client,
            )

    assert asyncio.run(scenario()) == "call_v1"
    assert seen["assistantId"] == "asst_1"
    assert seen["createdAtGt"].startswith("2026-08-13T11:58:30")


def test_platform_errors_resolve_to_none_rather_than_failing_the_run() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    async def scenario() -> str | None:
        async with _mock_client(handler) as client:
            return await resolve_platform_call_id(
                platform="retell",
                agent_id="agent_1",
                api_key="key",
                dialed_at=DIALED_AT,
                client=client,
            )

    assert asyncio.run(scenario()) is None


def test_platforms_without_a_lookup_are_unsupported() -> None:
    async def scenario() -> str | None:
        return await resolve_platform_call_id(
            platform="synthflow",
            agent_id="model_1",
            api_key="key",
            dialed_at=DIALED_AT,
        )

    assert asyncio.run(scenario()) is None


class BackloggedSip(FakeSip):
    """A softphone holding more buffered audio than one interval's worth.

    pyVoIP pads a read it cannot satisfy, which is how the reader learns it has
    caught up; anything still queued behind that point would otherwise be lost.
    """

    def __init__(self, chunks: list[bytes]) -> None:
        super().__init__()
        self.queued = list(chunks)
        self.reads = 0

    def read_audio(self, length: int = 160) -> bytes:
        self.reads += 1
        if self.queued:
            return self.queued.pop(0)
        return bytes([SILENCE_BYTE]) * length


def test_reader_drains_the_backlog_instead_of_falling_behind() -> None:
    sip = BackloggedSip([speech(800) for _ in range(4)])

    drained = mod._drain_audio(sip)

    # All four buffered chunks in one pass, then one read to hit the pad.
    assert len(drained) == 3_200
    assert sip.reads == 5


def test_drain_stops_at_the_padding_that_marks_a_caught_up_stream() -> None:
    sip = BackloggedSip([speech(800)])

    assert len(mod._drain_audio(sip)) == 800
    # Padding is dropped rather than spliced into the middle of speech.
    assert mod._drain_audio(sip) == b""


def test_drain_is_capped_so_one_pass_cannot_stall_the_loop() -> None:
    endless = BackloggedSip([])
    endless.read_audio = lambda length=160: speech(800)  # type: ignore[method-assign]

    assert len(mod._drain_audio(endless)) <= mod.DRAIN_LIMIT_BYTES + 800


def test_a_repeated_sentence_is_kept_as_its_own_turn(
    wired: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repetition is graded behaviour, so it must reach the judge.

    The streaming transports de-duplicate because they receive growing partials;
    here each flush is disjoint audio, so an identical sentence is the agent
    actually saying it twice.
    """
    monkeypatch.setattr(mod, "SILENCE_FLUSH_SECONDS", 0.05)
    monkeypatch.setattr(mod, "READ_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(mod, "RECEIVE_TIMEOUT_SECONDS", 5.0)
    line = "Just to confirm, zip codes are 5 digits."
    stt = FakeStt([line, line])
    monkeypatch.setattr(mod, "build_stt", lambda name: stt)
    # The gap must outlast the flush loop's own poll interval, or both
    # utterances land in one flush.
    sip = FakeSip(
        [speech(), speech()] + [silence()] * 60 + [speech(), speech()] + [silence()] * 60
    )
    sip.deactivate_when_drained = False
    transport = TwilioPstnTransport(sip_factory=lambda ep: sip)

    async def scenario() -> list[Any]:
        await transport.connect(target())
        await transport.receive()
        turns = [await transport.receive(), await transport.receive()]
        await transport.hangup()
        return turns

    assert [t.text for t in asyncio.run(scenario())] == [line, line]
