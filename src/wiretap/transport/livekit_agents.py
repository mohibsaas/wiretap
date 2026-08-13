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
from wiretap.providers.factory import build_stt
from wiretap.providers.speech import AudioBuffer
from wiretap.providers.tts import TTS_SAMPLE_RATE, synthesize_pcm
from wiretap.transport.base import Inbound, Transport


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
    _audio_buf: bytearray = field(default_factory=bytearray)
    _seen: set[str] = field(default_factory=set)

    def configure_speech(self, *, stt: str, tts: str, voice: str | None) -> None:
        self._stt_name = stt or self._stt_name
        self._tts_name = tts or self._tts_name
        self._voice = voice or self._voice

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
                loop = self._loop
                if loop and loop.is_running():
                    loop.call_soon_threadsafe(
                        lambda: asyncio.ensure_future(
                            self._consume_remote_audio(track), loop=loop
                        )
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
            pass

    async def send_text(self, text: str) -> None:
        if not self._connected or self._audio_source is None:
            raise RuntimeError("LiveKit transport not connected")
        from livekit import rtc

        pcm = await synthesize_pcm(
            text, voice=self._voice or "alloy", provider=self._tts_name
        )
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

    async def receive(self) -> Inbound:
        try:
            return await asyncio.wait_for(self._pending.get(), timeout=45.0)
        except TimeoutError:
            return Inbound(hung_up=True)

    async def hangup(self) -> None:
        self._connected = False
        room = self._room
        self._room = None
        self._audio_source = None
        if room is not None:
            await room.disconnect()

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
                self._record(pcm, sample_rate=frame.sample_rate)
                self._audio_buf.extend(pcm)
                # ~2s at 48k stereo-ish; use byte threshold
                if len(self._audio_buf) > 96_000:
                    chunk = bytes(self._audio_buf)
                    self._audio_buf.clear()
                    stt = build_stt(self._stt_name)
                    text = await stt.transcribe(
                        AudioBuffer(pcm=chunk, sample_rate=frame.sample_rate or 48_000)
                    )
                    text = (text or "").strip()
                    if text and text not in self._seen:
                        self._seen.add(text)
                        await self._pending.put(Inbound(text=text))
        except Exception:
            return

    def _handle_data(self, raw: bytes) -> None:
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        text = ""
        if isinstance(event, dict):
            text = str(
                event.get("text")
                or event.get("transcript")
                or (event.get("agent_response") if isinstance(event.get("agent_response"), str) else "")
                or ""
            ).strip()
            # Retell-style nested transcript list
            if not text and isinstance(event.get("transcript"), list):
                for utt in event["transcript"]:
                    if isinstance(utt, dict) and utt.get("role") in {"agent", "assistant"}:
                        content = str(utt.get("content") or "").strip()
                        if content and content not in self._seen:
                            self._seen.add(content)
                            loop = self._loop
                            if loop and loop.is_running():
                                loop.call_soon_threadsafe(
                                    self._pending.put_nowait, Inbound(text=content)
                                )
                return
        if text and text not in self._seen:
            self._seen.add(text)
            loop = self._loop
            if loop and loop.is_running():
                loop.call_soon_threadsafe(self._pending.put_nowait, Inbound(text=text))
