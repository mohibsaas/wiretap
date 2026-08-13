"""Transport ABC — talk to their live agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from wiretap.models import AgentTarget

if TYPE_CHECKING:
    from wiretap.suite.audio import CallRecorder


@dataclass
class Inbound:
    text: str | None = None
    hung_up: bool = False


@dataclass
class CallRef:
    """Identifies the finished call on the platform that hosted it."""

    platform: str
    call_id: str


class Transport(ABC):
    _recorder: CallRecorder | None = None

    def attach_recorder(self, recorder: CallRecorder | None) -> None:
        """Optional: capture mixed call PCM for evaluation playback."""
        self._recorder = recorder

    def call_ref(self) -> CallRef | None:
        """Handle for fetching post-call artifacts. None when unsupported."""
        return None

    def _record(self, pcm: bytes, *, sample_rate: int = 16_000) -> None:
        if self._recorder is not None and pcm:
            self._recorder.add(pcm, sample_rate=sample_rate)

    @abstractmethod
    async def connect(self, target: AgentTarget) -> None: ...

    @abstractmethod
    async def send_text(self, text: str) -> None: ...

    @abstractmethod
    async def receive(self) -> Inbound: ...

    @abstractmethod
    async def hangup(self) -> None: ...
