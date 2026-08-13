"""PSTN transport — dial the live agent's real phone number over Twilio.

Same shape as the WebSocket transports (queue of :class:`Inbound`, background
reader, silence-flush STT); only the pipe changes. A local softphone registers
to a Twilio SIP domain and Twilio bridges it to the agent's number with inline
TwiML, so no public endpoint is needed.

The platform's own call id does not exist until after the call, so tool-call
capture resolves it during hangup — see :mod:`wiretap.transport.platform_lookup`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from wiretap.models import AgentTarget
from wiretap.providers.factory import build_stt, build_tts
from wiretap.providers.speech import AudioBuffer
from wiretap.services.twilio_pstn import (
    SipEndpoint,
    ensure_sip_endpoint,
    hangup_call,
    normalize_e164,
    place_bridge_call,
    resolve_from_number,
    twilio_client,
)
from wiretap.transport.audio_util import downsample_pcm16
from wiretap.transport.base import CallRef, Inbound, Transport
from wiretap.transport.platform_lookup import resolve_platform_call_id
from wiretap.transport.pstn_audio import (
    FRAME_BYTES,
    STT_SAMPLE_RATE,
    is_speech,
    is_starved_read,
    pcm16_to_pstn,
    pstn_to_pcm16,
)
from wiretap.transport.sip_client import PyVoipSipClient, SipClient

# Twilio has to ring our softphone, and pyVoIP defers its call callback by ~1s.
ANSWER_TIMEOUT_SECONDS = 60.0
RECEIVE_TIMEOUT_SECONDS = 45.0
READ_CHUNK_BYTES = FRAME_BYTES * 5
READ_INTERVAL_SECONDS = 0.1
# Ceiling on one drain pass so a burst cannot stall the loop; 2 s of 8 kHz audio.
DRAIN_LIMIT_BYTES = FRAME_BYTES * 100
# Phone speakers pause mid-sentence. Cutting an utterance too early splits one
# agent turn into fragments, which the simulator then answers separately.
# Measured on a live call: pauses of 1.2 s+ mark real turn boundaries and their
# count is flat out to 2 s, while 0.6 s also catches mid-sentence breaths.
SILENCE_FLUSH_SECONDS = 1.5
# 200 ms at 16 kHz — below this an "utterance" is a blip, not a turn.
MIN_UTTERANCE_BYTES = 6_400
MAX_UTTERANCE_BYTES = 320_000

SipClientFactory = Callable[[SipEndpoint], SipClient]


@dataclass
class TwilioPstnTransport(Transport):
    """Places a real phone call to the agent and speaks to it with TTS/STT."""

    sip_factory: SipClientFactory | None = None
    _sip: SipClient | None = None
    _target: AgentTarget | None = None
    _pending: asyncio.Queue[Inbound] = field(default_factory=asyncio.Queue)
    _connected: bool = False
    _stt_name: str = "pyai"
    _tts_name: str = "pyai"
    _voice: str | None = None
    _reader_task: asyncio.Task | None = None
    _flush_task: asyncio.Task | None = None
    _audio_buf: bytearray = field(default_factory=bytearray)
    _last_audio_at: float = 0.0
    _call_sid: str = ""
    _dialed_at: datetime | None = None
    _platform_call_id: str | None = None

    def configure_speech(self, *, stt: str, tts: str, voice: str | None) -> None:
        self._stt_name = stt
        self._tts_name = tts
        self._voice = voice

    def call_ref(self) -> CallRef | None:
        target = self._target
        if not self._platform_call_id or target is None or not target.platform:
            return None
        return CallRef(platform=target.platform, call_id=self._platform_call_id)

    async def connect(self, target: AgentTarget) -> None:
        self._target = target
        to_number = normalize_e164(target.phone_number, field="agent phone number")
        from_number = resolve_from_number()
        if not from_number:
            raise RuntimeError(
                "No Twilio caller number selected. Run `wiretap simulate` in a "
                "terminal to pick one, or set TWILIO_FROM_NUMBER."
            )
        from_number = normalize_e164(from_number, field="caller number")

        client = await asyncio.to_thread(twilio_client)
        endpoint = await asyncio.to_thread(ensure_sip_endpoint, client)

        factory = self.sip_factory or _default_sip_client
        self._sip = factory(endpoint)
        await asyncio.to_thread(self._sip.start)

        self._dialed_at = datetime.now(UTC)
        self._call_sid = await asyncio.to_thread(
            place_bridge_call,
            to_number=to_number,
            from_number=from_number,
            sip_uri=endpoint.uri,
            client=client,
        )

        answered = await asyncio.to_thread(
            self._sip.wait_for_call, ANSWER_TIMEOUT_SECONDS
        )
        if not answered:
            await self.hangup()
            raise RuntimeError(
                f"Twilio never bridged the call to {to_number} within "
                f"{int(ANSWER_TIMEOUT_SECONDS)}s (check the Twilio console call log)."
            )

        self._connected = True
        self._reader_task = asyncio.create_task(self._reader())
        self._flush_task = asyncio.create_task(self._silence_flush_loop())
        await self._pending.put(Inbound(text=""))  # ready; the agent speaks first

    async def send_text(self, text: str) -> None:
        if not self._connected or self._sip is None:
            raise RuntimeError("not connected")
        tts = build_tts(self._tts_name, self._voice)
        audio = await tts.synthesize(text)
        self._record(
            downsample_pcm16(audio.pcm, audio.sample_rate, STT_SAMPLE_RATE),
            sample_rate=STT_SAMPLE_RATE,
        )
        payload = pcm16_to_pstn(audio.pcm, sample_rate=audio.sample_rate)
        await asyncio.to_thread(self._sip.write_audio, payload)

    async def receive(self) -> Inbound:
        try:
            return await asyncio.wait_for(
                self._pending.get(), timeout=RECEIVE_TIMEOUT_SECONDS
            )
        except TimeoutError:
            return Inbound(hung_up=True)

    async def hangup(self) -> None:
        self._connected = False
        if self._flush_task:
            self._flush_task.cancel()
        if self._reader_task:
            self._reader_task.cancel()
        if self._audio_buf:
            await self._flush_audio_stt()
        if self._sip is not None:
            await asyncio.to_thread(self._sip.stop)
            self._sip = None
        if self._call_sid:
            await asyncio.to_thread(hangup_call, self._call_sid)
        await self._resolve_platform_call()

    async def _reader(self) -> None:
        """Pull telephony audio, gate it on energy, hand utterances to STT."""
        sip = self._sip
        assert sip is not None
        loop = asyncio.get_running_loop()
        try:
            while self._connected:
                payload = await asyncio.to_thread(_drain_audio, sip)
                if payload:
                    pcm = pstn_to_pcm16(payload)
                    self._record(pcm, sample_rate=STT_SAMPLE_RATE)
                    # The line is never digitally silent, so buffering on
                    # "bytes arrived" would flush an endless stream of hiss.
                    if is_speech(pcm):
                        self._audio_buf.extend(pcm)
                        self._last_audio_at = loop.time()
                    elif self._audio_buf:
                        self._audio_buf.extend(pcm)
                    if len(self._audio_buf) > MAX_UTTERANCE_BYTES:
                        await self._flush_audio_stt()
                if not sip.is_active():
                    self._connected = False
                    await self._flush_audio_stt()
                    await self._pending.put(Inbound(hung_up=True))
                    return
                await asyncio.sleep(READ_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
        except (OSError, ConnectionError, RuntimeError):
            await self._pending.put(Inbound(hung_up=True))

    async def _silence_flush_loop(self) -> None:
        """STT only after a pause, so chunked audio becomes one utterance."""
        while self._connected:
            await asyncio.sleep(0.25)
            if not self._audio_buf or not self._last_audio_at:
                continue
            idle = asyncio.get_running_loop().time() - self._last_audio_at
            if (
                idle >= SILENCE_FLUSH_SECONDS
                and len(self._audio_buf) >= MIN_UTTERANCE_BYTES
            ):
                await self._flush_audio_stt()

    async def _flush_audio_stt(self) -> None:
        if len(self._audio_buf) < MIN_UTTERANCE_BYTES:
            self._audio_buf.clear()
            return
        pcm = bytes(self._audio_buf)
        self._audio_buf.clear()
        stt = build_stt(self._stt_name)
        text = await stt.transcribe(AudioBuffer(pcm=pcm, sample_rate=STT_SAMPLE_RATE))
        if not _is_speech_transcript(text):
            return
        # No prefix de-duplication here, unlike the streaming transports: each
        # flush is a disjoint stretch of audio rather than a growing partial, so
        # an identical sentence is the agent genuinely repeating itself — which
        # is behaviour the judge is meant to see.
        await self._pending.put(Inbound(text=text.strip()))

    async def _resolve_platform_call(self) -> None:
        """Recover the platform's call id so tool-call capture can run."""
        target = self._target
        if target is None or self._platform_call_id or self._dialed_at is None:
            return
        token_env = target.token_env or _default_token_env(target.platform)
        if not token_env:
            return
        try:
            from wiretap.providers.env import require_env

            api_key = require_env(token_env)
        except (RuntimeError, ValueError):
            return
        self._platform_call_id = await resolve_platform_call_id(
            platform=target.platform or "",
            agent_id=target.agent_id,
            api_key=api_key,
            dialed_at=self._dialed_at,
            phone_number=target.phone_number,
        )


def _drain_audio(sip: SipClient) -> bytes:
    """Read until pyVoIP runs dry, so the loop can never fall behind the call.

    Reading exactly one interval's worth per interval leaves no room for
    scheduling jitter: pyVoIP advances its buffer only by the bytes it really
    had, so any delay becomes a backlog that is never repaid and the tail of the
    call is lost at hangup. Draining to the starve point keeps us level, and the
    padding that marks that point is dropped rather than spliced into speech.
    """
    chunks: list[bytes] = []
    total = 0
    while total < DRAIN_LIMIT_BYTES:
        payload = sip.read_audio(READ_CHUNK_BYTES)
        if is_starved_read(payload):
            break
        chunks.append(payload)
        total += len(payload)
    return b"".join(chunks)


def _default_sip_client(endpoint: SipEndpoint) -> SipClient:
    return PyVoipSipClient(
        domain=endpoint.domain,
        username=endpoint.username,
        password=endpoint.password,
    )


def _default_token_env(platform: str | None) -> str | None:
    from wiretap.toolcalls import retell, vapi

    return {
        "retell": retell.DEFAULT_TOKEN_ENV,
        "vapi": vapi.DEFAULT_TOKEN_ENV,
    }.get((platform or "").lower().strip())


def _is_speech_transcript(text: str) -> bool:
    """Ringback and line noise transcribe to nothing usable — not agent turns."""
    stripped = (text or "").strip()
    return len(stripped) >= 2 and any(c.isalpha() for c in stripped)


__all__ = ["ANSWER_TIMEOUT_SECONDS", "TwilioPstnTransport"]
