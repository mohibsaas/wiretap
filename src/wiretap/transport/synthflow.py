"""Synthflow outbound WebSocket media transport (connect-then-bind).

Requires:
  SYNTHFLOW_API_KEY
  SYNTHFLOW_FROM_NUMBER / SYNTHFLOW_TO_NUMBER (E.164) — API still expects phones
    for outbound-test-ws-media even when streaming media over WS.

Uses L16 @ 16 kHz with payload framing for STT/TTS-friendly PCM.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field

import httpx

from wiretap.models import AgentTarget
from wiretap.providers.env import require_env
from wiretap.providers.tts import TTS_SAMPLE_RATE, synthesize_pcm
from wiretap.transport.audio_util import (
    downsample_pcm16,
    pad_pcm16_silence,
    pcm16be_to_le,
    pcm16le_to_be,
)
from wiretap.transport.base import Inbound, Transport
from wiretap.transport.turn_gate import (
    AgentTurnGate,
    receive_coalesced,
    speak_with_gate_mute,
)

SYNTHFLOW_API = "https://api.synthflow.ai"
_TARGET_RATE = 16_000
_FRAME_BYTES = 640  # 20ms L16 @ 16kHz mono


@dataclass
class SynthflowTransport(Transport):
    _ws: object | None = None
    _pending: asyncio.Queue[Inbound] = field(default_factory=asyncio.Queue)
    _connected: bool = False
    _recv_task: asyncio.Task | None = None
    _tts_name: str = "pyai"
    _stt_name: str = "pyai"
    _voice: str | None = "alloy"
    _gate: AgentTurnGate | None = None
    _call_id: str | None = None

    def configure_speech(self, *, stt: str, tts: str, voice: str | None) -> None:
        self._stt_name = stt or self._stt_name
        self._tts_name = tts or self._tts_name
        self._voice = voice or self._voice
        if self._gate is not None:
            self._gate.configure(stt=self._stt_name)

    async def connect(self, target: AgentTarget) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError(
                "Synthflow transport requires websockets. Reinstall with: uv sync"
            ) from exc

        model_id = target.agent_id
        if not model_id:
            raise ValueError("Synthflow transport requires agent.agent_id (modelId)")
        key = require_env(target.token_env or "SYNTHFLOW_API_KEY")
        from_num = (os.environ.get("SYNTHFLOW_FROM_NUMBER") or "").strip()
        to_num = (os.environ.get("SYNTHFLOW_TO_NUMBER") or "").strip()
        if not from_num or not to_num:
            raise RuntimeError(
                "Synthflow live dial needs SYNTHFLOW_FROM_NUMBER and "
                "SYNTHFLOW_TO_NUMBER (E.164) in the environment. "
                "Import still works without them."
            )

        headers = {"Authorization": f"Bearer {key}"}
        async with httpx.AsyncClient(timeout=45.0) as client:
            base_resp = await client.get(
                f"{SYNTHFLOW_API}/v2/calls/outbound-test-ws-media/base-url",
                headers=headers,
            )
            if base_resp.is_error:
                raise RuntimeError(
                    f"Synthflow base-url failed ({base_resp.status_code}): "
                    f"{base_resp.text[:300]}"
                )
            base_payload = base_resp.json() or {}
            ws_url = (
                base_payload.get("wsMediaBaseUrl")
                or base_payload.get("url")
                or base_payload.get("baseUrl")
            )
            if not ws_url and isinstance(base_payload.get("data"), dict):
                data = base_payload["data"]
                ws_url = data.get("wsMediaBaseUrl") or data.get("url")
            if not ws_url:
                raise RuntimeError("Synthflow base-url response missing wsMediaBaseUrl")

        self._ws = await websockets.connect(ws_url)
        # Step 2: server_info
        raw = await asyncio.wait_for(self._ws.recv(), timeout=20.0)
        info = json.loads(raw) if isinstance(raw, str) else {}
        if info.get("type") != "server_info":
            raise RuntimeError(f"Expected Synthflow server_info, got: {info!r}")
        server_name = info.get("server-name") or info.get("server_name")
        if not server_name:
            raise RuntimeError("Synthflow server_info missing server-name")

        async with httpx.AsyncClient(timeout=45.0) as client:
            start = await client.post(
                f"{SYNTHFLOW_API}/v2/calls/outbound-test-ws-media",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "modelId": model_id,
                    "fromPhoneNumber": from_num,
                    "toPhoneNumber": to_num,
                    "leadName": "wiretap",
                    "agentVersion": "draft",
                    "wsMediaCodec": "l16",
                    "wsMediaFraming": "payload",
                    "wsMediaServerName": server_name,
                },
            )
            if start.is_error:
                raise RuntimeError(
                    f"Synthflow start call failed ({start.status_code}): {start.text[:300]}"
                )
            started = start.json() or {}
            sid = started.get("sid")
            self._call_id = started.get("callId")
            if not sid:
                raise RuntimeError("Synthflow start call returned no sid")

        await self._ws.send(json.dumps({"type": "bind", "sid": sid}))
        call_info_raw = await asyncio.wait_for(self._ws.recv(), timeout=20.0)
        call_info = json.loads(call_info_raw) if isinstance(call_info_raw, str) else {}
        if call_info.get("type") != "call_info":
            raise RuntimeError(f"Expected Synthflow call_info, got: {call_info!r}")

        self._gate = AgentTurnGate(
            stt_name=self._stt_name,
            on_utterance=self._on_agent_utterance,
        )
        self._sync_gate_elapsed()
        await self._gate.start()
        self._connected = True
        self._recv_task = asyncio.create_task(self._reader())

    async def send_text(self, text: str) -> None:
        if not self._connected or self._ws is None:
            raise RuntimeError("Synthflow transport not connected")

        pcm_task = asyncio.create_task(
            synthesize_pcm(
                text, voice=self._voice or "alloy", provider=self._tts_name
            )
        )

        async def _publish() -> None:
            assert self._ws is not None
            pcm = await pcm_task
            if len(pcm) < TTS_SAMPLE_RATE // 5:
                raise RuntimeError(
                    "Caller TTS returned empty/too-short audio — "
                    "check speech.tts provider and voice id"
                )
            pcm16 = downsample_pcm16(pcm, TTS_SAMPLE_RATE, _TARGET_RATE)
            pcm16 = pad_pcm16_silence(pcm16, sample_rate=_TARGET_RATE)
            self._record(pcm16, sample_rate=_TARGET_RATE)
            be = pcm16le_to_be(pcm16)
            for i in range(0, len(be), _FRAME_BYTES):
                frame = be[i : i + _FRAME_BYTES]
                if len(frame) < _FRAME_BYTES:
                    frame = frame + b"\x00" * (_FRAME_BYTES - len(frame))
                await self._ws.send(frame)
                await asyncio.sleep(0.02)

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
                if isinstance(message, str):
                    continue
                if isinstance(message, bytes):
                    le = pcm16be_to_le(message)
                    self._record(le, sample_rate=_TARGET_RATE)
                    if self._gate is not None:
                        self._gate.push(le, sample_rate=_TARGET_RATE)
        except asyncio.CancelledError:
            raise
        except (OSError, ConnectionError, RuntimeError):
            await self._pending.put(Inbound(hung_up=True))
