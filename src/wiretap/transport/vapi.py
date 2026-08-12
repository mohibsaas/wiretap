"""Vapi text Chat transport — secondary / CI fallback.

Prefer voice (VapiWebSocketTransport). Opt in with transport: text or
agent.room_url: chat|text against the same assistant via POST /chat.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

from wiretap.models import AgentTarget
from wiretap.providers.env import require_env
from wiretap.transport.base import Inbound, Transport

VAPI_API = "https://api.vapi.ai"


@dataclass
class VapiTransport(Transport):
    """Live Vapi assistant over the Chat API."""

    _client: httpx.AsyncClient | None = None
    _assistant_id: str | None = None
    _chat_id: str | None = None
    _pending: asyncio.Queue[Inbound] = field(default_factory=asyncio.Queue)
    _connected: bool = False
    _awaiting_user_first: bool = False

    async def connect(self, target: AgentTarget) -> None:
        agent_id = target.agent_id
        if not agent_id:
            raise ValueError("Vapi transport requires agent.agent_id (assistant id).")
        key = require_env(target.token_env or "VAPI_API_KEY")
        self._assistant_id = agent_id
        self._client = httpx.AsyncClient(
            base_url=VAPI_API,
            headers={"Authorization": f"Bearer {key}"},
            timeout=60.0,
        )
        self._connected = True

        # Prefer assistant firstMessage when present; else user speaks first.
        greeting = await self._fetch_first_message(agent_id)
        if greeting:
            await self._pending.put(Inbound(text=greeting))
        else:
            # Signal ready without a fake agent line (runner skips empty text)
            self._awaiting_user_first = True
            await self._pending.put(Inbound(text=""))

    async def send_text(self, text: str) -> None:
        if not self._connected or not self._client or not self._assistant_id:
            raise RuntimeError("Vapi transport not connected")
        reply = await self._chat(text)
        if reply:
            await self._pending.put(Inbound(text=reply))
        else:
            await self._pending.put(Inbound(hung_up=True))

    async def receive(self) -> Inbound:
        try:
            return await asyncio.wait_for(self._pending.get(), timeout=60.0)
        except TimeoutError:
            return Inbound(hung_up=True)

    async def hangup(self) -> None:
        self._connected = False
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _fetch_first_message(self, assistant_id: str) -> str | None:
        assert self._client
        resp = await self._client.get(f"/assistant/{assistant_id}")
        if resp.status_code != 200:
            return None
        data = resp.json()
        msg = data.get("firstMessage") or data.get("first_message")
        return str(msg).strip() if msg else None

    async def _chat(self, text: str) -> str:
        assert self._client and self._assistant_id
        body: dict = {"assistantId": self._assistant_id, "input": text}
        if self._chat_id:
            body["previousChatId"] = self._chat_id
        resp = await self._client.post("/chat", json=body)
        resp.raise_for_status()
        data = resp.json()
        self._chat_id = data.get("id") or self._chat_id
        return _extract_vapi_output(data)


def _extract_vapi_output(data: dict) -> str:
    output = data.get("output") or []
    parts: list[str] = []
    if isinstance(output, list):
        for item in output:
            if isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, str) and content.strip():
                    parts.append(content.strip())
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            t = block.get("text")
                            if t:
                                parts.append(str(t))
            elif isinstance(item, str):
                parts.append(item)
    elif isinstance(output, str):
        parts.append(output)
    return "\n".join(parts).strip()
