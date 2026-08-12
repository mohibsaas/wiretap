"""Text stub transport so local runs work without a live platform."""

from __future__ import annotations

from dataclasses import dataclass, field

from wiretap.models import AgentTarget
from wiretap.transport.base import Inbound, Transport


@dataclass
class TextEchoTransport(Transport):
    _queue: list[Inbound] = field(default_factory=list)
    _ok: bool = False

    async def connect(self, target: AgentTarget) -> None:
        _ = target
        self._ok = True
        self._queue.append(
            Inbound(text="Hi, thanks for calling. How can I help you today?")
        )

    async def send_text(self, text: str) -> None:
        if not self._ok:
            raise RuntimeError("not connected")
        lower = text.lower()
        if "manager" in lower or "transfer" in lower:
            reply = "I can transfer you to a manager. Please hold."
        elif "cancel" in lower or "refund" in lower:
            reply = (
                "I can help cancel. The prorated refund policy applies to unused time. "
                "I've noted your cancellation request."
            )
        else:
            reply = "Got it. Could you tell me a bit more about what you need?"
        self._queue.append(Inbound(text=reply))

    async def receive(self) -> Inbound:
        if self._queue:
            return self._queue.pop(0)
        return Inbound(hung_up=True)

    async def hangup(self) -> None:
        self._ok = False
