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
    # Human-readable title for UI/CLI (prefer this over id)
    name: str = ""
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
    # Tool names the live agent must invoke to satisfy this scenario
    expected_tools: list[str] = Field(default_factory=list)
    rules: RuleCheck = Field(default_factory=RuleCheck)
    beats: list[Beat] = Field(default_factory=list)
    # Optional multi-step phases: [{id, task, max_turns}]
    flow_phases: list[dict] = Field(default_factory=list)
    # Category tag for grouping in UI / reports (emotional, compliance, …)
    category: str | None = None


class AgentTarget(BaseModel):
    """How to reach the live agent under test."""

    transport: TransportKind = TransportKind.TEXT
    platform: str | None = None  # vapi|retell|elevenlabs|livekit|synthflow|bolna|bland|None
    agent_id: str | None = None
    room_url: str | None = None
    # E.164 number to dial when transport is pstn
    phone_number: str | None = None
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


class JudgeMetricSpec(BaseModel):
    """Deprecated — kept so older suite YAML still loads."""

    weight: float = 1.0
    threshold: float = 0.7
    required: bool = True
    description: str = ""


def default_judge_metrics() -> dict[str, JudgeMetricSpec]:
    """No multi-rubric pack — goal match is a single score."""
    return {}


class JudgeConfig(BaseModel):
    """Suite-level judge gate — goal / success-criteria match score."""

    # Bands: score < fail_below → fail; fail_below ≤ score < pass_threshold → partial;
    # score ≥ pass_threshold → pass.
    fail_below: float = 0.5
    pass_threshold: float = 0.7
    # Deprecated fields (ignored by the goal-match judge; kept for YAML compat).
    pass_mode: str = "goal_match"
    metrics: dict[str, JudgeMetricSpec] = Field(default_factory=dict)


class SuiteConfig(BaseModel):
    agent: AgentTarget = Field(default_factory=AgentTarget)
    models: ModelSlots = Field(default_factory=ModelSlots)
    speech: SpeechConfig = Field(default_factory=SpeechConfig)
    mode: SimulationMode = Field(default_factory=SimulationMode)
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    personas: list[Persona]
    scenarios: list[Scenario]


class TurnRecord(BaseModel):
    role: str  # user | agent
    text: str
    intended_text: str | None = None
    # Offset into the mixed call WAV (CallRecorder timeline), when known.
    start_ms: float | None = None
    end_ms: float | None = None


class MetricScore(BaseModel):
    """Deprecated multi-rubric row — kept for old artifacts."""

    id: str
    score: float
    passed: bool
    threshold: float = 0.7
    required: bool = True
    weight: float = 1.0
    rationale: str = ""


class ToolCallRecord(BaseModel):
    """One tool invocation the live agent made, as reported by its platform.

    Values are sanitized before they get here — they reach both disk and the
    judge LLM. ``turn_index`` is best-effort: the platform transcript and the
    transcript our transport observed do not align 1:1, so it positions a call
    for display but is never a join key.
    """

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_summary: str = ""
    status: str = "unknown"  # ok | error | unknown
    turn_index: int | None = None
    at_seconds: float | None = None


class JudgeResult(BaseModel):
    passed: bool
    score: float | None = None  # 0–1 goal match (UI shows as %)
    verdict: str = "fail"  # fail | partial | pass
    reason: str
    suggestions: list[str] = Field(default_factory=list)
    metrics: list[MetricScore] = Field(default_factory=list)  # unused (compat)
    pass_mode: str = "goal_match"
    fail_below: float = 0.5
    pass_at: float = 0.7


class RuleResult(BaseModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)


class SimulationArtifact(BaseModel):
    """One scenario simulation result (test agent ↔ live agent ↔ judge)."""

    simulation_id: str = ""
    created_at: str = ""
    # Parent evaluation run (batch / suite execution)
    batch_id: str = ""
    suite_id: str
    scenario_id: str
    scenario_name: str = ""
    persona_id: str
    persona_name: str = ""
    passed: bool
    transcript: list[TurnRecord]
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    judge: JudgeResult
    rules: RuleResult
    metrics: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    # Relative to .wiretap/ when present (e.g. simulations/audio/<id>.wav)
    audio_path: str | None = None


__all__ = [
    "AgentTarget",
    "Beat",
    "JudgeConfig",
    "JudgeMetricSpec",
    "JudgeResult",
    "MetricScore",
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
    "ToolCallRecord",
    "TransportKind",
    "TurnRecord",
    "default_judge_metrics",
]
