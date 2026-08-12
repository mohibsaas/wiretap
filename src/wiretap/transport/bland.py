"""Bland pathway transport — starts a Bland call when phone config is present.

Requires `agent.room_url` as an E.164 number (Bland is phone-first).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

from wiretap.models import AgentTarget
from wiretap.providers.env import require_env
from wiretap.transport.base import Inbound, Transport

BLAND_API = "https://api.bland.ai"


@dataclass
class BlandTransport(Transport):
    """Best-effort Bland live path via POST /v1/calls (phone).

    Text turn-taking is not offered by Bland the same way as Vapi Chat; this
    transport records call creation and surfaces status for CI smoke.
    Prefer import + editing suites; use PSTN when you need full fidelity.
    """

    _client: httpx.AsyncClient | None = None
    _call_id: str | None = None
    _pending: asyncio.Queue[Inbound] = field(default_factory=asyncio.Queue)
    _connected: bool = False

    async def connect(self, target: AgentTarget) -> None:
        pathway_id = target.agent_id
        if not pathway_id:
            raise ValueError("Bland transport requires agent.agent_id (pathway id).")
        phone = None
        # Optional: room_url misused as phone E.164 for outbound
        if target.room_url and target.room_url.startswith("+"):
            phone = target.room_url
        if not phone:
            raise RuntimeError(
                "Bland live runs need a phone number. Set agent.room_url to an E.164 "
                "number (e.g. +15551234567) for outbound, or use import for suite "
                "generation only."
            )
        key = require_env(target.token_env or "BLAND_API_KEY")
        self._client = httpx.AsyncClient(
            base_url=BLAND_API,
            headers={"authorization": key},
            timeout=60.0,
        )
        resp = await self._client.post(
            "/v1/calls",
            json={
                "phone_number": phone,
                "pathway_id": pathway_id,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._call_id = str(data.get("call_id") or data.get("status") or "")
        self._connected = True
        await self._pending.put(
            Inbound(
                text=(
                    f"Bland call started (id={self._call_id}). "
                    "Full transcript polling is limited; prefer webhook/PSTN for fidelity."
                )
            )
        )

    async def send_text(self, text: str) -> None:
        _ = text
        # Bland phone calls are not text-interactive via this API
        await self._pending.put(Inbound(hung_up=True))

    async def receive(self) -> Inbound:
        try:
            return await asyncio.wait_for(self._pending.get(), timeout=30.0)
        except TimeoutError:
            return Inbound(hung_up=True)

    async def hangup(self) -> None:
        self._connected = False
        if self._client:
            await self._client.aclose()
            self._client = None
