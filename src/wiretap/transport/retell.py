"""Retell live transport — create-web-call + LiveKit room.

Turn detection uses the shared ``AgentTurnGate`` (energy VAD + batch STT),
same as other live audio transports — not Retell-specific talk events.
After hangup, Get Call supplies the judge transcript when available.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

from wiretap.models import AgentTarget, TurnRecord
from wiretap.providers.env import require_env
from wiretap.providers.tts import TTS_SAMPLE_RATE, synthesize_pcm
from wiretap.transport.audio_util import pad_pcm16_silence
from wiretap.transport.base import Inbound, Transport
from wiretap.transport.transcript_util import normalize_agent_text, utterance_timing_ms
from wiretap.transport.turn_gate import (
    AgentTurnGate,
    receive_coalesced,
    speak_with_gate_mute,
)
from wiretap.transport.livekit_util import disconnect_livekit_room, schedule_on_loop

RETELL_API = "https://api.retellai.com"
RETELL_LIVEKIT_URL = "wss://retell-ai-4ihahnq7.livekit.cloud"


@dataclass
class RetellTransport(Transport):
    _room: object | None = None
    _audio_source: object | None = None
    _pending: asyncio.Queue[Inbound] = field(default_factory=asyncio.Queue)
    _connected: bool = False
    _call_id: str | None = None
    _api_key: str | None = None
    _loop: asyncio.AbstractEventLoop | None = None
    _tts_name: str = "pyai"
    _stt_name: str = "pyai"
    _voice: str | None = "alloy"
    _gate: AgentTurnGate | None = None

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
                "Retell live transport requires livekit. "
                "Reinstall with: uv sync"
            ) from exc

        agent_id = target.agent_id
        if not agent_id:
            raise ValueError("Retell transport requires agent.agent_id.")
        key = require_env(target.token_env or "RETELL_API_KEY")
        self._api_key = key

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

        self._gate = AgentTurnGate(
            stt_name=self._stt_name,
            on_utterance=self._on_agent_utterance,
        )
        self._sync_gate_elapsed()
        await self._gate.start()

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

        @room.on("disconnected")
        def _on_disconnected(*_args: object) -> None:
            schedule_on_loop(self._loop, self._mark_hung_up)

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

        try:
            inbound = await asyncio.wait_for(self._pending.get(), timeout=20.0)
            await self._pending.put(inbound)
        except TimeoutError:
            pass

    async def send_text(self, text: str) -> None:
        if not self._connected or self._audio_source is None:
            raise RuntimeError("Retell transport not connected")
        from livekit import rtc

        # Start TTS immediately so synthesis overlaps gate mute setup.
        pcm_task = asyncio.create_task(
            synthesize_pcm(
                text, voice=self._voice or "alloy", provider=self._tts_name
            )
        )

        async def _publish() -> None:
            assert self._audio_source is not None
            pcm = await pcm_task
            if len(pcm) < TTS_SAMPLE_RATE // 5:  # < ~0.2s of audio
                raise RuntimeError(
                    "Caller TTS returned empty/too-short audio — "
                    "check speech.tts provider and voice id"
                )
            pcm = pad_pcm16_silence(pcm, sample_rate=TTS_SAMPLE_RATE)
            self._record(pcm, sample_rate=TTS_SAMPLE_RATE)
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

    async def _mark_hung_up(self) -> None:
        if not self._connected:
            return
        self._connected = False
        await self._pending.put(Inbound(hung_up=True))

    async def hangup(self) -> None:
        # Drop loop ref first so FFI/thread callbacks stop scheduling work.
        self._connected = False
        self._loop = None
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

    async def fetch_final_transcript(self) -> list[TurnRecord] | None:
        """Pull Retell's completed call transcript (preferred for judging)."""
        call_id = self._call_id
        key = self._api_key
        if not call_id or not key:
            return None

        payload: dict | None = None
        async with httpx.AsyncClient(timeout=20.0) as client:
            for _ in range(15):
                resp = await client.get(
                    f"{RETELL_API}/v2/get-call/{call_id}",
                    headers={"Authorization": f"Bearer {key}"},
                )
                if resp.is_error:
                    await asyncio.sleep(0.6)
                    continue
                payload = resp.json()
                status = str(payload.get("call_status") or "").lower()
                has_obj = isinstance(payload.get("transcript_object"), list)
                has_text = bool(str(payload.get("transcript") or "").strip())
                if status in {"ended", "error", "analyzed"} and (has_obj or has_text):
                    break
                if has_obj or has_text:
                    break
                await asyncio.sleep(0.6)
            else:
                return None

        if not payload:
            return None

        turns: list[TurnRecord] = []
        obj = payload.get("transcript_object")
        if isinstance(obj, list) and obj:
            for utt in obj:
                if not isinstance(utt, dict):
                    continue
                role = str(utt.get("role") or "").lower()
                content = normalize_agent_text(str(utt.get("content") or ""))
                if not content:
                    continue
                start_ms, end_ms = utterance_timing_ms(utt)
                if role == "agent":
                    turns.append(
                        TurnRecord(
                            role="agent",
                            text=content,
                            start_ms=start_ms,
                            end_ms=end_ms,
                        )
                    )
                elif role == "user":
                    turns.append(
                        TurnRecord(
                            role="user",
                            text=content,
                            start_ms=start_ms,
                            end_ms=end_ms,
                        )
                    )
            return turns or None

        raw = str(payload.get("transcript") or "").strip()
        if not raw:
            return None
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            lower = line.lower()
            if lower.startswith("agent:"):
                turns.append(TurnRecord(role="agent", text=line.split(":", 1)[1].strip()))
            elif lower.startswith("user:"):
                turns.append(TurnRecord(role="user", text=line.split(":", 1)[1].strip()))
        return turns or None

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
