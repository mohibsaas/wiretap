"""Test-agent orchestrator — turn-based control plane for simulate.

Ladder:
  1. Single-node prompt (no ``flow_phases``)
  2. Beats pin critical lines
  3. Multi-phase flow from ``scenario.flow_phases``

Voice STT/TTS lives on the transport; this module only decides what to say.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from wiretap.agent.beats import beat_for_turn
from wiretap.models import Beat, Persona, TurnRecord
from wiretap.prompts.test_agent import (
    TEST_AGENT_MAIN_TASK,
    TEST_AGENT_NEXT_REPLY,
    agent_said_message,
    caller_role_message,
    phase_task_message,
)
from wiretap.providers.llm import complete


@dataclass
class FlowNode:
    """One step in the test-agent dialogue policy."""

    id: str
    role_message: str
    task_messages: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.id,
            "role_message": self.role_message,
            "task_messages": self.task_messages,
        }


def phases_to_nodes(
    *,
    persona: Persona,
    success_criteria: str,
    phases: list[dict[str, Any]] | None,
) -> list[FlowNode]:
    """Build an ordered node list from suite phases (or one default node)."""
    role = caller_role_message(
        identity=persona.identity,
        goal=persona.goal,
        personality=persona.personality or "neutral",
        success_criteria=success_criteria,
    )
    if not phases:
        return [
            FlowNode(
                id="main",
                role_message=role,
                task_messages=[
                    {
                        "role": "system",
                        "content": TEST_AGENT_MAIN_TASK,
                    }
                ],
            )
        ]

    out: list[FlowNode] = []
    for i, phase in enumerate(phases):
        node_id = str(phase.get("id") or f"phase_{i}")
        task = phase.get("task") or phase.get("name") or "continue the call"
        is_last = i == len(phases) - 1
        out.append(
            FlowNode(
                id=node_id,
                role_message=role,
                task_messages=[
                    {
                        "role": "system",
                        "content": phase_task_message(
                            node_id=node_id, task=str(task), is_last=is_last
                        ),
                    }
                ],
            )
        )
    return out


class TestAgentOrchestrator:
    """Turn-based dialogue policy for the wiretap test agent."""

    __test__ = False  # not a pytest test class

    def __init__(
        self,
        *,
        persona: Persona,
        success_criteria: str,
        model: str,
        phases: list[dict[str, Any]] | None = None,
        beats: list[Beat] | None = None,
        temperature: float = 0.5,
        speech: dict[str, Any] | None = None,
    ) -> None:
        self.persona = persona
        self.success_criteria = success_criteria
        self.model = model
        self.beats = beats or []
        self.temperature = temperature
        # Speech ids for artifacts only. Live TTS/STT is on the transport.
        self.speech = speech
        self.nodes = phases_to_nodes(
            persona=persona,
            success_criteria=success_criteria,
            phases=phases,
        )
        self._phase_meta = phases or []
        self._node_idx = 0
        self._turns_in_node = 0
        self._caller_turn = 0
        self._engine = "test_agent"
        self.history: list[dict[str, str]] = []
        self._enter_node(0)

    @property
    def current_node_id(self) -> str:
        return self.nodes[self._node_idx].id

    @property
    def flow_graph(self) -> list[dict[str, Any]]:
        """Serializable phase graph for artifacts."""
        return [n.as_dict() for n in self.nodes]

    def describe(self) -> dict[str, Any]:
        return {
            "orchestrator": self._engine,
            "current_node": self.current_node_id,
            "nodes": self.flow_graph,
            "speech": self.speech,
        }

    def _enter_node(self, idx: int) -> None:
        self._node_idx = idx
        self._turns_in_node = 0
        cfg = self.nodes[idx]
        self.history = [{"role": "system", "content": cfg.role_message}]
        for msg in cfg.task_messages:
            if msg.get("content"):
                self.history.append(
                    {"role": str(msg.get("role") or "system"), "content": str(msg["content"])}
                )

    def observe_agent(self, text: str) -> None:
        self.history.append({"role": "user", "content": agent_said_message(text)})

    def next_utterance(self) -> tuple[str, bool]:
        self._caller_turn += 1
        self._turns_in_node += 1
        beat = beat_for_turn(self.beats, self._caller_turn)
        if beat and beat.say:
            text = beat.say.strip()
            self.history.append({"role": "assistant", "content": text})
            return text, False

        self.history.append(
            {
                "role": "user",
                "content": TEST_AGENT_NEXT_REPLY,
            }
        )
        text = complete(
            model=self.model,
            messages=self.history,
            temperature=self.temperature,
        )
        self.history.append({"role": "assistant", "content": text})

        hangup = "[[HANGUP]]" in text
        phase_done = "[[PHASE_DONE]]" in text
        clean = text.replace("[[HANGUP]]", "").replace("[[PHASE_DONE]]", "").strip()

        if beat and beat.must_include and beat.must_include.lower() not in clean.lower():
            clean = f"{clean} {beat.must_include}".strip()

        max_turns = 8
        if self._phase_meta and self._node_idx < len(self._phase_meta):
            max_turns = int(self._phase_meta[self._node_idx].get("max_turns") or 4)

        if phase_done or self._turns_in_node >= max_turns:
            if self._node_idx < len(self.nodes) - 1:
                self._enter_node(self._node_idx + 1)
            elif phase_done and not hangup:
                hangup = True

        return clean, hangup

    def as_turn(self, text: str) -> TurnRecord:
        return TurnRecord(role="user", text=text, intended_text=text)


def build_orchestrator(
    *,
    persona: Persona,
    success_criteria: str,
    model: str,
    phases: list[dict[str, Any]] | None = None,
    beats: list[Beat] | None = None,
    temperature: float = 0.5,
    stt: str = "pyai",
    tts: str = "pyai",
    voice: str | None = "alloy",
) -> TestAgentOrchestrator:
    return TestAgentOrchestrator(
        persona=persona,
        success_criteria=success_criteria,
        model=model,
        phases=phases,
        beats=beats,
        temperature=temperature,
        speech={"stt": stt, "tts": tts, "voice": voice},
    )


__all__ = [
    "FlowNode",
    "TestAgentOrchestrator",
    "build_orchestrator",
    "phases_to_nodes",
]
