"""Vapi WebSocket transport — primary live voice path.

Creates a call with transport.provider=vapi.websocket and streams TTS PCM.
Agent audio is received as binary; STT via speech factory.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import httpx

from wiretap.models import AgentTarget
from wiretap.providers.env import require_env
from wiretap.providers.factory import build_stt, build_tts
from wiretap.providers.speech import AudioBuffer
from wiretap.transport.base import Inbound, Transport
from wiretap.transport.transcript_util import accept_final_utterance, is_vapi_final_transcript

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
    _audio_buf: bytearray = field(default_factory=bytearray)
    _seen_agent: set[str] = field(default_factory=set)
    _last_audio_at: float = 0.0
    _flush_task: asyncio.Task | None = None

    def configure_speech(self, *, stt: str, tts: str, voice: str | None) -> None:
        self._stt_name = stt
        self._tts_name = tts
        self._voice = voice

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

        self._ws = await websockets.connect(ws_url)
        self._connected = True
        self._recv_task = asyncio.create_task(self._reader())
        self._flush_task = asyncio.create_task(self._silence_flush_loop())
        await self._pending.put(Inbound(text=""))  # ready; may speak first via audio

    async def send_text(self, text: str) -> None:
        if not self._connected or self._ws is None:
            raise RuntimeError("not connected")
        tts = build_tts(self._tts_name, self._voice)
        audio = await tts.synthesize(text)
        # naive resample skip — send as-is; Vapi expects 16k; OpenAI PCM is 24k
        # Downsample 24k→16k roughly by dropping samples
        pcm = _downsample_24k_to_16k(audio.pcm)
        self._record(pcm, sample_rate=16_000)
        await self._ws.send(pcm)

    async def receive(self) -> Inbound:
        try:
            return await asyncio.wait_for(self._pending.get(), timeout=45.0)
        except TimeoutError:
            return Inbound(hung_up=True)

    async def hangup(self) -> None:
        self._connected = False
        if self._flush_task:
            self._flush_task.cancel()
        if self._recv_task:
            self._recv_task.cancel()
        if self._audio_buf:
            await self._flush_audio_stt()
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _silence_flush_loop(self) -> None:
        """STT only after a short pause so chunked audio is one utterance."""
        try:
            while self._connected:
                await asyncio.sleep(0.25)
                if not self._audio_buf or not self._last_audio_at:
                    continue
                idle = asyncio.get_running_loop().time() - self._last_audio_at
                if idle >= 0.6 and len(self._audio_buf) >= 3200:
                    await self._flush_audio_stt()
        except asyncio.CancelledError:
            raise

    async def _flush_audio_stt(self) -> None:
        if not self._audio_buf:
            return
        pcm = bytes(self._audio_buf)
        self._audio_buf.clear()
        stt = build_stt(self._stt_name)
        text = await stt.transcribe(AudioBuffer(pcm=pcm, sample_rate=16_000))
        accepted = accept_final_utterance(text, self._seen_agent)
        if accepted:
            await self._pending.put(Inbound(text=accepted))

    async def _reader(self) -> None:
        assert self._ws is not None
        try:
            async for message in self._ws:
                if isinstance(message, bytes):
                    self._record(message, sample_rate=16_000)
                    self._audio_buf.extend(message)
                    self._last_audio_at = asyncio.get_running_loop().time()
                    # Hard cap so we never hold unbounded audio.
                    if len(self._audio_buf) > 160_000:
                        await self._flush_audio_stt()
                elif isinstance(message, str):
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") != "transcript" or data.get("role") != "assistant":
                        continue
                    # Partials stream like Retell prefixes — only finals are turns.
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
    # 24000/16000 = 1.5 → take 2 of every 3
    i = 0
    while i < len(samples):
        out.append(samples[i])
        i += 1
        if i < len(samples):
            out.append(samples[i])
            i += 2
    return out.tobytes()
