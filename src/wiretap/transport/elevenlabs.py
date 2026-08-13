"""ElevenLabs Conversational AI WebSocket transport.

Uses signed URL + ConvAI events. Caller lines go as TTS PCM (user_audio_chunk);
agent replies are taken from agent_response text events (no STT required).
"""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass, field

import httpx

from wiretap.models import AgentTarget
from wiretap.providers.env import require_env
from wiretap.providers.tts import TTS_SAMPLE_RATE, synthesize_pcm
from wiretap.transport.base import Inbound, Transport
from wiretap.transport.audio_util import downsample_pcm16

ELEVEN_API = "https://api.elevenlabs.io"
# Match our TTS output to avoid resample when possible
@dataclass
class ElevenLabsTransport(Transport):
    _ws: object | None = None
    _pending: asyncio.Queue[Inbound] = field(default_factory=asyncio.Queue)
    _connected: bool = False
    _recv_task: asyncio.Task | None = None
    _tts_name: str = "pyai"
    _voice: str | None = "alloy"
    _seen: set[str] = field(default_factory=set)

    def configure_speech(self, *, stt: str, tts: str, voice: str | None) -> None:
        self._tts_name = tts or self._tts_name
        self._voice = voice or self._voice

    async def connect(self, target: AgentTarget) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError(
                "ElevenLabs transport requires websockets. Reinstall with: uv sync"
            ) from exc

        agent_id = target.agent_id
        if not agent_id:
            raise ValueError("ElevenLabs transport requires agent.agent_id")
        key = require_env(target.token_env or "ELEVENLABS_API_KEY")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{ELEVEN_API}/v1/convai/conversation/get-signed-url",
                params={"agent_id": agent_id},
                headers={"xi-api-key": key},
            )
            if resp.is_error:
                raise RuntimeError(
                    f"ElevenLabs signed URL failed ({resp.status_code}): {resp.text[:300]}"
                )
            signed = (resp.json() or {}).get("signed_url")
        if not signed:
            raise RuntimeError("ElevenLabs get-signed-url returned no signed_url")

        self._ws = await websockets.connect(signed)
        self._connected = True
        # Minimal initiation; audio format follows the agent config / metadata reply.
        await self._ws.send(json.dumps({"type": "conversation_initiation_client_data"}))
        self._recv_task = asyncio.create_task(self._reader())

        # Wait briefly for greeting / metadata
        try:
            inbound = await asyncio.wait_for(self._pending.get(), timeout=12.0)
            await self._pending.put(inbound)
        except TimeoutError:
            pass

    async def send_text(self, text: str) -> None:
        if not self._connected or self._ws is None:
            raise RuntimeError("ElevenLabs transport not connected")
        # Prefer audio path (live voice); also send user_message as text fallback path
        pcm = await synthesize_pcm(
            text, voice=self._voice or "alloy", provider=self._tts_name
        )
        if TTS_SAMPLE_RATE != 24_000:
            pcm = downsample_pcm16(pcm, TTS_SAMPLE_RATE, 24_000)
        self._record(pcm, sample_rate=24_000)
        chunk_size = 24_000 * 2 // 10  # ~100ms
        for i in range(0, len(pcm), chunk_size):
            piece = pcm[i : i + chunk_size]
            await self._ws.send(
                json.dumps({"user_audio_chunk": base64.b64encode(piece).decode("ascii")})
            )

    async def receive(self) -> Inbound:
        try:
            return await asyncio.wait_for(self._pending.get(), timeout=45.0)
        except TimeoutError:
            return Inbound(hung_up=True)

    async def hangup(self) -> None:
        self._connected = False
        if self._recv_task:
            self._recv_task.cancel()
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _reader(self) -> None:
        assert self._ws is not None
        try:
            async for message in self._ws:
                if not isinstance(message, str):
                    continue
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    continue
                typ = data.get("type")
                if typ == "ping":
                    ping = data.get("ping_event") or {}
                    event_id = ping.get("event_id")
                    delay_ms = float(ping.get("ping_ms") or 0)
                    if delay_ms > 0:
                        await asyncio.sleep(delay_ms / 1000.0)
                    await self._ws.send(json.dumps({"type": "pong", "event_id": event_id}))
                    continue
                if typ == "agent_response":
                    evt = data.get("agent_response_event") or {}
                    text = str(evt.get("agent_response") or "").strip()
                    if text and text not in self._seen:
                        self._seen.add(text)
                        await self._pending.put(Inbound(text=text))
                    continue
                if typ == "audio":
                    evt = data.get("audio_event") or {}
                    b64 = evt.get("audio_base_64") or evt.get("audio_base64")
                    if b64:
                        try:
                            pcm = base64.b64decode(b64)
                            self._record(pcm, sample_rate=16_000)
                        except Exception:
                            pass
        except asyncio.CancelledError:
            raise
        except (OSError, ConnectionError, RuntimeError):
            await self._pending.put(Inbound(hung_up=True))
