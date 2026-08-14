"""Test-agent orchestrator — turn-based control plane for simulate.

Ladder:
  1. Single-node prompt (no ``flow_phases``)
  2. Beats pin critical lines
  3. Multi-phase flow from ``scenario.flow_phases``

Voice STT/TTS lives on the transport; this module only decides what to say.
"""

from __future__ import annotations

import re
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
from wiretap.providers.llm import acomplete

# Dialog turns carried across a phase boundary. Phases exist for long calls, so
# the whole history would grow the prompt without bound.
MAX_CARRIED_DIALOG = 12

# Models emit the control sentinels with stray case and spacing ("[[ hangup ]]").
# Anything left in the text is spoken aloud to the live agent, so strip loosely…
_SENTINEL = re.compile(r"\[\[\s*(HANGUP|PHASE_DONE)\s*\]\]", re.IGNORECASE)
# …but only act on sentinels that actually end the utterance: a model narrating
# "I'll send [[HANGUP]] when we're done" must not hang up mid-call.
_TRAILING_SENTINEL = re.compile(
    r"\[\[\s*(HANGUP|PHASE_DONE)\s*\]\][\s.!?,;:\"')\]]*$", re.IGNORECASE
)


def split_sentinels(text: str) -> tuple[str, bool, bool]:
    """Spoken text with sentinels removed, plus ``(hangup, phase_done)``.

    Both sentinels can arrive together in either order, so the tail is peeled
    repeatedly rather than tested once.
    """
    hangup = False
    phase_done = False
    tail = (text or "").strip()
    while True:
        match = _TRAILING_SENTINEL.search(tail)
        if not match:
            break
        if match.group(1).upper() == "HANGUP":
            hangup = True
        else:
            phase_done = True
        tail = tail[: match.start()].strip()
    clean = re.sub(r"\s{2,}", " ", _SENTINEL.sub(" ", tail)).strip()
    return clean, hangup, phase_done


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
        constraints=list(persona.constraints or []),
        knowledge=dict(persona.knowledge or {}),
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
        # Spoken dialog only, kept apart from history because the control
        # messages we inject also carry the "user" role.
        self._dialog: list[dict[str, str]] = []
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
        # Phases are steps within ONE call: without the earlier dialog the caller
        # re-introduces itself and re-asks what it already got answered.
        self.history.extend(self._dialog[-MAX_CARRIED_DIALOG:])

    def _record(self, role: str, content: str) -> None:
        turn = {"role": role, "content": content}
        self.history.append(turn)
        self._dialog.append(turn)

    def observe_agent(self, text: str) -> None:
        self._record("user", agent_said_message(text))

    async def next_utterance(self) -> tuple[str, bool]:
        self._caller_turn += 1
        self._turns_in_node += 1
        beat = beat_for_turn(self.beats, self._caller_turn)
        if beat and beat.say:
            text = beat.say.strip()
            self._record("assistant", text)
            return text, False

        # The nudge is not persisted: repeating it every turn would stack copies
        # of the same instruction in a long call.
        # Must be async — sync LiteLLM blocks the whole event loop and
        # serializes concurrent scenario dials.
        text = await acomplete(
            model=self.model,
            messages=[
                *self.history,
                {"role": "user", "content": TEST_AGENT_NEXT_REPLY},
            ],
            temperature=self.temperature,
        )
        self._record("assistant", text)

        clean, hangup, phase_done = split_sentinels(text)

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
    "MAX_CARRIED_DIALOG",
    "FlowNode",
    "TestAgentOrchestrator",
    "build_orchestrator",
    "phases_to_nodes",
    "split_sentinels",
]
