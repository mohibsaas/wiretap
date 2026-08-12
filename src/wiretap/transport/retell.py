"""Retell live transport — create-web-call + LiveKit room.

Joins Retell's LiveKit cloud (same as the official web SDK), publishes TTS audio
for caller lines, and reads agent text from LiveKit data-channel transcript updates.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import httpx

from wiretap.models import AgentTarget
from wiretap.providers.env import require_env
from wiretap.providers.tts import TTS_SAMPLE_RATE, synthesize_pcm
from wiretap.transport.base import Inbound, Transport

RETELL_API = "https://api.retellai.com"
RETELL_LIVEKIT_URL = "wss://retell-ai-4ihahnq7.livekit.cloud"


@dataclass
class RetellTransport(Transport):
    _room: object | None = None
    _audio_source: object | None = None
    _pending: asyncio.Queue[Inbound] = field(default_factory=asyncio.Queue)
    _seen_agent: set[str] = field(default_factory=set)
    _connected: bool = False
    _call_id: str | None = None
    _loop: asyncio.AbstractEventLoop | None = None
    _tts_name: str = "pyai"
    _voice: str | None = "alloy"

    def configure_speech(self, *, stt: str, tts: str, voice: str | None) -> None:
        self._tts_name = tts or self._tts_name
        self._voice = voice or self._voice

    async def connect(self, target: AgentTarget) -> None:
        try:
            from livekit import rtc
        except ImportError as exc:
            raise RuntimeError(
                "Retell live transport requires livekit. "
                "Reinstall with: uv sync"
            ) from exc

        agent_id = target.agent_id
        if not agent_id:
            raise ValueError("Retell transport requires agent.agent_id.")
        key = require_env(target.token_env or "RETELL_API_KEY")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{RETELL_API}/v2/create-web-call",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={"agent_id": agent_id},
            )
            if resp.status_code == 403:
                detail = ""
                try:
                    detail = str((resp.json() or {}).get("message") or resp.text)
                except Exception:
                    detail = resp.text
                raise RuntimeError(
                    "Retell create-web-call forbidden (403). "
                    "Your RETELL_API_KEY needs the Testing.Write scope "
                    "(Retell dashboard → API keys). "
                    f"Details: {detail}"
                )
            if resp.is_error:
                raise RuntimeError(
                    f"Retell create-web-call failed ({resp.status_code}): "
                    f"{resp.text[:300]}"
                )
            payload = resp.json()

        access_token = payload.get("access_token")
        self._call_id = payload.get("call_id")
        if not access_token:
            raise RuntimeError("Retell create-web-call returned no access_token")

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
            await asyncio.wait_for(room.connect(RETELL_LIVEKIT_URL, access_token), timeout=30.0)
        except TimeoutError as exc:
            raise RuntimeError(
                "Timed out joining Retell LiveKit room (30s). "
                "Check network / Retell status and retry."
            ) from exc

        source = rtc.AudioSource(TTS_SAMPLE_RATE, 1)
        track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
        await room.local_participant.publish_track(track)
        self._audio_source = source
        self._connected = True

        # Wait briefly for agent greeting on the data channel
        try:
            inbound = await asyncio.wait_for(self._pending.get(), timeout=15.0)
            # put it back so receive() gets it
            await self._pending.put(inbound)
        except TimeoutError:
            pass

    async def send_text(self, text: str) -> None:
        if not self._connected or self._audio_source is None:
            raise RuntimeError("Retell transport not connected")
        from livekit import rtc

        pcm = await synthesize_pcm(text, voice=self._voice or "alloy", provider=self._tts_name)
        self._record(pcm, sample_rate=TTS_SAMPLE_RATE)
        # Push PCM16 as AudioFrames
        samples_per_channel = TTS_SAMPLE_RATE // 50  # 20ms frames
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
        # Remainder
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
        """Best-effort capture of agent audio for evaluation playback."""
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
                self._record(bytes(frame.data), sample_rate=frame.sample_rate)
        except Exception:
            # Recording must never break the call
            return

    def _handle_data(self, raw: bytes) -> None:
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if event.get("event_type") != "update":
            return
        transcript = event.get("transcript") or []
        if not isinstance(transcript, list):
            return
        for utt in transcript:
            if not isinstance(utt, dict):
                continue
            if utt.get("role") != "agent":
                continue
            content = str(utt.get("content") or "").strip()
            if not content or content in self._seen_agent:
                continue
            self._seen_agent.add(content)
            loop = self._loop
            if loop and loop.is_running():
                loop.call_soon_threadsafe(self._pending.put_nowait, Inbound(text=content))
