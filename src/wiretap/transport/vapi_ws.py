"""Vapi WebSocket transport — primary live voice path.

Creates a call with transport.provider=vapi.websocket and streams TTS PCM.
Turn detection uses shared ``AgentTurnGate`` (same as Retell/LiveKit/Synthflow).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import httpx

from wiretap.models import AgentTarget
from wiretap.providers.env import require_env
from wiretap.providers.factory import build_tts
from wiretap.transport.audio_util import pad_pcm16_silence
from wiretap.transport.base import Inbound, Transport
from wiretap.transport.transcript_util import accept_final_utterance, is_vapi_final_transcript
from wiretap.transport.turn_gate import (
    AgentTurnGate,
    receive_coalesced,
    speak_with_gate_mute,
)

VAPI_API = "https://api.vapi.ai"


@dataclass
class VapiWebSocketTransport(Transport):
    _ws: object | None = None
    _pending: asyncio.Queue[Inbound] = field(default_factory=asyncio.Queue)
    _connected: bool = False
    _stt_name: str = "pyai"
    _tts_name: str = "pyai"
    _voice: str | None = None
    _recv_task: asyncio.Task | None = None
    _gate: AgentTurnGate | None = None
    _seen_agent: set[str] = field(default_factory=set)

    def configure_speech(self, *, stt: str, tts: str, voice: str | None) -> None:
        self._stt_name = stt
        self._tts_name = tts
        self._voice = voice
        if self._gate is not None:
            self._gate.configure(stt=self._stt_name)

    async def connect(self, target: AgentTarget) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError(
                "Vapi WebSocket voice transport requires websockets. "
                "Reinstall with: uv sync"
            ) from exc

        agent_id = target.agent_id
        if not agent_id:
            raise ValueError("Vapi WS transport requires agent.agent_id")
        key = require_env(target.token_env or "VAPI_API_KEY")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{VAPI_API}/call",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "assistantId": agent_id,
                    "transport": {
                        "provider": "vapi.websocket",
                        "audioFormat": {
                            "format": "pcm_s16le",
                            "container": "raw",
                            "sampleRate": 16000,
                        },
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()

        ws_url = (data.get("transport") or {}).get("websocketCallUrl")
        if not ws_url:
            raise RuntimeError("Vapi call response missing transport.websocketCallUrl")

        self._gate = AgentTurnGate(
            stt_name=self._stt_name,
            on_utterance=self._on_agent_utterance,
        )
        self._sync_gate_elapsed()
        await self._gate.start()

        self._ws = await websockets.connect(ws_url)
        self._connected = True
        self._recv_task = asyncio.create_task(self._reader())
        await self._pending.put(Inbound(text=""))  # ready; may speak first via audio

    async def send_text(self, text: str) -> None:
        if not self._connected or self._ws is None:
            raise RuntimeError("not connected")

        pcm_task = asyncio.create_task(
            build_tts(self._tts_name, self._voice).synthesize(text)
        )

        async def _publish() -> None:
            assert self._ws is not None
            audio = await pcm_task
            if not audio.pcm or len(audio.pcm) < 24000 // 5:
                raise RuntimeError(
                    "Caller TTS returned empty/too-short audio — "
                    "check speech.tts provider and voice id"
                )
            pcm = _downsample_24k_to_16k(audio.pcm)
            pcm = pad_pcm16_silence(pcm, sample_rate=16_000)
            self._record(pcm, sample_rate=16_000)
            await self._ws.send(pcm)

        await speak_with_gate_mute(self._gate, _publish)

    async def receive(self) -> Inbound:
        return await receive_coalesced(
            self._pending, self._gate, connected=self._connected
        )

    async def hangup(self) -> None:
        self._connected = False
        if self._recv_task:
            self._recv_task.cancel()
        gate = self._gate
        self._gate = None
        if gate is not None:
            await gate.stop()
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _on_agent_utterance(
        self,
        text: str,
        start_ms: float | None = None,
        end_ms: float | None = None,
    ) -> None:
        await self._pending.put(
            Inbound(text=text, start_ms=start_ms, end_ms=end_ms)
        )

    async def _reader(self) -> None:
        assert self._ws is not None
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    self._record(message, sample_rate=16_000)
                    if self._gate is not None:
                        self._gate.push(message, sample_rate=16_000)
                elif isinstance(message, str):
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") != "transcript" or data.get("role") != "assistant":
                        continue
                    # Optional finals — audio gate remains the primary turn path.
                    if not is_vapi_final_transcript(data):
                        continue
                    t = data.get("transcript") or data.get("text")
                    accepted = accept_final_utterance(str(t or ""), self._seen_agent)
                    if accepted:
                        await self._pending.put(Inbound(text=accepted))
        except asyncio.CancelledError:
            raise
        except (OSError, ConnectionError, RuntimeError):
            await self._pending.put(Inbound(hung_up=True))


def _downsample_24k_to_16k(pcm24: bytes) -> bytes:
    """Very naive 3:2 drop for MVP."""
    import array

    samples = array.array("h")
    samples.frombytes(pcm24[: len(pcm24) - (len(pcm24) % 2)])
    out = array.array("h")
    i = 0
    while i < len(samples):
        out.append(samples[i])
        i += 1
        if i < len(samples):
            out.append(samples[i])
            i += 2
    return out.tobytes()
