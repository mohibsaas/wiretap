"""Simulation progress events — shared by CLI display and (optionally) UI batches."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

SimPhase = Literal[
    "queued",
    "connecting",
    "waiting_agent",
    "turn",
    "hanging_up",
    "judging",
    "saving",
    "finished",
    "failed",
]


@dataclass(frozen=True)
class SimEvent:
    """One progress pulse from a running simulation."""

    phase: SimPhase
    scenario_id: str
    scenario_name: str = ""
    detail: str = ""
    turn: int = 0
    role: str | None = None
    text: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


ProgressHandler = Callable[[SimEvent], None]


def truncate(text: str, n: int = 72) -> str:
    t = " ".join((text or "").split())
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"
