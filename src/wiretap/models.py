"""Shared schemas for suites and simulation artifacts."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TransportKind(str, Enum):
    TEXT = "text"
    WEBRTC = "webrtc"
    SIP = "sip"
    PSTN = "pstn"


class Beat(BaseModel):
    """Pinned caller behavior at a turn (Level 2)."""

    at_turn: int | None = None
    after_turns: int | None = None
    say: str | None = None
    must_include: str | None = None


class Persona(BaseModel):
    id: str
    identity: str
    goal: str
    personality: str = ""
    constraints: list[str] = Field(default_factory=list)
    knowledge: dict[str, Any] = Field(default_factory=dict)


class RuleCheck(BaseModel):
    includes: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    id: str
    name: str
    persona_id: str
    max_turns: int = 20
    success_criteria: str
    rubric: str = ""
    rules: RuleCheck = Field(default_factory=RuleCheck)
    beats: list[Beat] = Field(default_factory=list)
    # Optional multi-step phases: [{id, task, max_turns}]
    flow_phases: list[dict] = Field(default_factory=list)
    # Category tag for grouping in UI / reports (emotional, compliance, …)
    category: str | None = None


class AgentTarget(BaseModel):
    """How to reach the live agent under test."""

    transport: TransportKind = TransportKind.TEXT
    platform: str | None = None  # vapi | retell | bland | livekit | None
    agent_id: str | None = None
    room_url: str | None = None
    # Never put tokens in YAML — reference env var names only
    token_env: str | None = None


class ModelSlots(BaseModel):
    simulator: str = "gpt-4o-mini"
    judge: str = "gpt-4o-mini"


class SpeechConfig(BaseModel):
    """pyai is the documented default; adapters are optional extras."""

    stt: str = "pyai"
    tts: str = "pyai"
    voice: str | None = None


class SimulationMode(BaseModel):
    """Test-agent / CI behavior knobs for a simulation."""

    strict: bool = False
    temperature: float = 0.5


# Backward-compatible alias
RunMode = SimulationMode


class SuiteConfig(BaseModel):
    agent: AgentTarget = Field(default_factory=AgentTarget)
    models: ModelSlots = Field(default_factory=ModelSlots)
    speech: SpeechConfig = Field(default_factory=SpeechConfig)
    mode: SimulationMode = Field(default_factory=SimulationMode)
    personas: list[Persona]
    scenarios: list[Scenario]


class TurnRecord(BaseModel):
    role: str  # user | agent
    text: str
    intended_text: str | None = None


class JudgeResult(BaseModel):
    passed: bool
    score: float | None = None
    reason: str
    suggestions: list[str] = Field(default_factory=list)


class RuleResult(BaseModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)


class SimulationArtifact(BaseModel):
    """One scenario simulation result (test agent ↔ live agent ↔ judge)."""

    simulation_id: str = ""
    created_at: str = ""
    suite_id: str
    scenario_id: str
    persona_id: str
    passed: bool
    transcript: list[TurnRecord]
    judge: JudgeResult
    rules: RuleResult
    metrics: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AgentTarget",
    "Beat",
    "JudgeResult",
    "ModelSlots",
    "Persona",
    "RuleCheck",
    "RuleResult",
    "RunMode",
    "Scenario",
    "SimulationArtifact",
    "SimulationMode",
    "SpeechConfig",
    "SuiteConfig",
    "TransportKind",
    "TurnRecord",
]
