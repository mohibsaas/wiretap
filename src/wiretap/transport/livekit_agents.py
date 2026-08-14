"""Generic LiveKit Agents transport — join a room with a minted JWT.

Suite fields:
  platform: livekit
  agent_id: room name
  room_url: wss://… LiveKit URL
  token_env: LIVEKIT_API_KEY (API secret from LIVEKIT_API_SECRET)

Optional: pre-minted LIVEKIT_TOKEN bypasses minting.
Agent text comes from remote audio STT (generic agents rarely share Retell transcripts).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field

from wiretap.models import AgentTarget
from wiretap.providers.env import require_env
from wiretap.providers.tts import TTS_SAMPLE_RATE, synthesize_pcm
from wiretap.transport.audio_util import pad_pcm16_silence
from wiretap.transport.base import Inbound, Transport
from wiretap.transport.transcript_util import accept_final_utterance
from wiretap.transport.turn_gate import (
    AgentTurnGate,
    receive_coalesced,
    speak_with_gate_mute,
)
from wiretap.transport.livekit_util import disconnect_livekit_room, schedule_on_loop


def mint_livekit_jwt(
    *,
    api_key: str,
    api_secret: str,
    identity: str,
    room: str,
    ttl_sec: int = 3600,
) -> str:
    """HS256 LiveKit access token (stdlib only — no livekit-api package)."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": api_key,
        "sub": identity,
        "name": identity,
        "nbf": now,
        "exp": now + ttl_sec,
        "video": {
            "roomJoin": True,
            "room": room,
            "canPublish": True,
            "canSubscribe": True,
            "canPublishData": True,
        },
    }

    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    h = _b64(json.dumps(header, separators=(",", ":")).encode())
    p = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()
    sig = hmac.new(api_secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64(sig)}"


@dataclass
class LiveKitTransport(Transport):
    _room: object | None = None
    _audio_source: object | None = None
    _pending: asyncio.Queue[Inbound] = field(default_factory=asyncio.Queue)
    _connected: bool = False
    _loop: asyncio.AbstractEventLoop | None = None
    _tts_name: str = "pyai"
    _stt_name: str = "pyai"
    _voice: str | None = "alloy"
    _gate: AgentTurnGate | None = None
    _seen: set[str] = field(default_factory=set)
    _draft_agent: str = ""
    _agent_talking: bool = False

    def configure_speech(self, *, stt: str, tts: str, voice: str | None) -> None:
        self._stt_name = stt or self._stt_name
        self._tts_name = tts or self._tts_name
        self._voice = voice or self._voice
        if self._gate is not None:
            self._gate.configure(stt=self._stt_name)

    async def connect(self, target: AgentTarget) -> None:
        try:
            from livekit import rtc
        except ImportError as exc:
            raise RuntimeError(
                "LiveKit transport requires livekit. Reinstall with: uv sync"
            ) from exc

        room_name = target.agent_id
        room_url = (target.room_url or os.environ.get("LIVEKIT_URL") or "").strip()
        if not room_name:
            raise ValueError("LiveKit transport requires agent.agent_id (room name)")
        if not room_url or room_url.lower() in {"chat", "text"}:
            raise ValueError(
                "LiveKit transport requires agent.room_url (wss://…livekit…) "
                "or LIVEKIT_URL in the environment."
            )

        token = (os.environ.get("LIVEKIT_TOKEN") or "").strip()
        if not token:
            api_key = require_env(target.token_env or "LIVEKIT_API_KEY")
            api_secret = require_env("LIVEKIT_API_SECRET")
            token = mint_livekit_jwt(
                api_key=api_key,
                api_secret=api_secret,
                identity="wiretap-caller",
                room=room_name,
            )

        self._loop = asyncio.get_running_loop()
        room = rtc.Room()
        self._room = room

        self._gate = AgentTurnGate(
            stt_name=self._stt_name,
            on_utterance=self._on_agent_utterance,
        )
        self._sync_gate_elapsed()
        await self._gate.start()

        @room.on("data_received")
        def _on_data(data: rtc.DataPacket) -> None:
            self._handle_data(bytes(data.data))

        @room.on("track_subscribed")
        def _on_track(
            track: rtc.Track,
            _publication: rtc.RemoteTrackPublication,
            _participant: rtc.RemoteParticipant,
        ) -> None:
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                schedule_on_loop(
                    self._loop, lambda: self._consume_remote_audio(track)
                )

        try:
            await asyncio.wait_for(room.connect(room_url, token), timeout=30.0)
        except TimeoutError as exc:
            raise RuntimeError("Timed out joining LiveKit room (30s).") from exc

        source = rtc.AudioSource(TTS_SAMPLE_RATE, 1)
        track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
        await room.local_participant.publish_track(track)
        self._audio_source = source
        self._connected = True

        try:
            inbound = await asyncio.wait_for(self._pending.get(), timeout=12.0)
            await self._pending.put(inbound)
        except TimeoutError:
            if self._draft_agent:
                self._commit_draft()

    async def send_text(self, text: str) -> None:
        if not self._connected or self._audio_source is None:
            raise RuntimeError("LiveKit transport not connected")
        from livekit import rtc

        pcm_task = asyncio.create_task(
            synthesize_pcm(
                text, voice=self._voice or "alloy", provider=self._tts_name
            )
        )

        async def _publish() -> None:
            assert self._audio_source is not None
            pcm = await pcm_task
            if len(pcm) < TTS_SAMPLE_RATE // 5:
                raise RuntimeError(
                    "Caller TTS returned empty/too-short audio — "
                    "check speech.tts provider and voice id"
                )
            pcm = pad_pcm16_silence(pcm, sample_rate=TTS_SAMPLE_RATE)
            self._record(pcm, sample_rate=TTS_SAMPLE_RATE)
            samples_per_channel = TTS_SAMPLE_RATE // 50
            offset = 0
            while offset + samples_per_channel * 2 <= len(pcm):
                chunk = pcm[offset : offset + samples_per_channel * 2]
                offset += samples_per_channel * 2
                frame = rtc.AudioFrame(
                    data=chunk,
                    sample_rate=TTS_SAMPLE_RATE,
                    num_channels=1,
                    samples_per_channel=samples_per_channel,
                )
                await self._audio_source.capture_frame(frame)
            rem = pcm[offset:]
            if rem:
                pad = rem + b"\x00" * (samples_per_channel * 2 - len(rem))
                frame = rtc.AudioFrame(
                    data=pad[: samples_per_channel * 2],
                    sample_rate=TTS_SAMPLE_RATE,
                    num_channels=1,
                    samples_per_channel=samples_per_channel,
                )
                await self._audio_source.capture_frame(frame)

        await speak_with_gate_mute(self._gate, _publish)

    async def receive(self) -> Inbound:
        return await receive_coalesced(
            self._pending, self._gate, connected=self._connected
        )

    async def hangup(self) -> None:
        self._connected = False
        self._loop = None
        if self._draft_agent:
            try:
                self._commit_draft()
            except Exception:
                pass
        gate = self._gate
        self._gate = None
        room = self._room
        self._room = None
        self._audio_source = None
        if gate is not None:
            try:
                await asyncio.shield(gate.stop())
            except Exception:
                pass
        await disconnect_livekit_room(room)

    async def _on_agent_utterance(
        self,
        text: str,
        start_ms: float | None = None,
        end_ms: float | None = None,
    ) -> None:
        await self._pending.put(
            Inbound(text=text, start_ms=start_ms, end_ms=end_ms)
        )

    async def _consume_remote_audio(self, track: object) -> None:
        try:
            from livekit import rtc
        except ImportError:
            return
        if not isinstance(track, rtc.RemoteAudioTrack):
            return
        stream = rtc.AudioStream(track)
        try:
            async for event in stream:
                if not self._connected:
                    break
                frame = event.frame
                pcm = bytes(frame.data)
                rate = int(frame.sample_rate or 16_000)
                self._record(pcm, sample_rate=rate)
                if self._gate is not None:
                    self._gate.push(pcm, sample_rate=rate)
        except Exception:
            return

    def _handle_data(self, raw: bytes) -> None:
        """Optional data-channel text (not required for turn-taking)."""
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(event, dict):
            return

        et = str(event.get("event_type") or "")
        if et == "agent_start_talking":
            self._agent_talking = True
            return
        if et == "agent_stop_talking":
            self._agent_talking = False
            self._commit_draft()
            return

        # Nested Retell-style transcript list
        if isinstance(event.get("transcript"), list):
            latest_agent = ""
            last_role = ""
            for utt in event["transcript"]:
                if not isinstance(utt, dict):
                    continue
                role = str(utt.get("role") or "")
                content = str(utt.get("content") or "").strip()
                if not content:
                    continue
                last_role = role
                if role in {"agent", "assistant"}:
                    latest_agent = content
            if latest_agent:
                if (
                    self._draft_agent
                    and latest_agent != self._draft_agent
                    and not latest_agent.startswith(self._draft_agent)
                    and not self._draft_agent.startswith(latest_agent)
                ):
                    self._commit_draft()
                self._draft_agent = latest_agent
            if last_role == "user" and self._draft_agent:
                self._commit_draft()
            return

        text = str(
            event.get("text")
            or (
                event.get("transcript")
                if isinstance(event.get("transcript"), str)
                else ""
            )
            or (
                event.get("agent_response")
                if isinstance(event.get("agent_response"), str)
                else ""
            )
            or ""
        ).strip()
        if not text:
            return
        self._draft_agent = text
        if isinstance(event.get("agent_response"), str) or et not in {
            "update",
            "",
        }:
            if not self._agent_talking:
                self._commit_draft()

    def _commit_draft(self) -> None:
        text = accept_final_utterance(self._draft_agent, self._seen)
        self._draft_agent = ""
        if not text:
            return
        inbound = Inbound(text=text)
        loop = self._loop
        if loop is None:
            return
        try:
            if loop.is_closed():
                return
        except Exception:
            return
        if loop.is_running():
            try:
                loop.call_soon_threadsafe(self._pending.put_nowait, inbound)
            except RuntimeError:
                return
        else:
            try:
                self._pending.put_nowait(inbound)
            except Exception:
                return
