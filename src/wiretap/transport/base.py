"""Transport ABC — talk to their live agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from wiretap.models import AgentTarget


@dataclass
class Inbound:
    text: str | None = None
    hung_up: bool = False


class Transport(ABC):
    @abstractmethod
    async def connect(self, target: AgentTarget) -> None: ...

    @abstractmethod
    async def send_text(self, text: str) -> None: ...

    @abstractmethod
    async def receive(self) -> Inbound: ...

    @abstractmethod
    async def hangup(self) -> None: ...
