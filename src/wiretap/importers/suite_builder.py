"""Build a SuiteConfig (+ optional AgentGraph) from imported platform text."""

from __future__ import annotations

import re
from typing import Any

from wiretap.ir.agent_graph import AgentGraph
from wiretap.models import (
    AgentTarget,
    Beat,
    ModelSlots,
    Persona,
    RuleCheck,
    Scenario,
    SpeechConfig,
    SuiteConfig,
    TransportKind,
)


def suite_from_prompt(
    *,
    platform: str,
    agent_id: str,
    agent_name: str,
    system_prompt: str,
    first_message: str = "",
    graph: AgentGraph | None = None,
) -> SuiteConfig:
    """Heuristic default suite — no LLM required for import."""
    goal = _guess_goal(system_prompt, agent_name)
    persona = Persona(
        id="imported_caller",
        identity=f"A customer calling {agent_name or 'the agent'}",
        goal=goal,
        personality="clear and patient",
        constraints=["Do not reveal you are a test bot"],
    )
    beats: list[Beat] = [
        Beat(at_turn=1, say=first_message.strip() or "Hi, I need some help today."),
    ]
    success = (
        f"Agent handles the call appropriately given its role. "
        f"Inferred goal for the caller: {goal}"
    )
    scenarios = [
        Scenario(
            id="smoke",
            name="Imported smoke scenario",
            persona_id=persona.id,
            max_turns=10,
            success_criteria=success,
            rubric=(
                "Pass if the agent stays on-policy and helps toward the caller's goal. "
                "Fail if it invents facts or ignores clear user intent."
            ),
            rules=RuleCheck(),
            beats=beats,
        )
    ]
    if graph and len(graph.nodes) > 1:
        scenarios.append(
            Scenario(
                id="flow_coverage",
                name="Exercise main flow paths",
                persona_id=persona.id,
                max_turns=14,
                success_criteria=(
                    "Caller progresses through the agent's main flow; "
                    f"known nodes: {', '.join(graph.node_ids()[:8])}"
                ),
                rubric="Pass if the agent advances the conversation without dead-ending.",
                beats=[Beat(at_turn=1, say="Hi, let's get started.")],
            )
        )

    return SuiteConfig(
        agent=AgentTarget(
            transport=TransportKind.WEBRTC,
            platform=platform,
            agent_id=agent_id,
            token_env=f"{platform.upper()}_API_KEY",
        ),
        models=ModelSlots(),
        speech=SpeechConfig(),
        personas=[persona],
        scenarios=scenarios,
    )


def _guess_goal(prompt: str, agent_name: str) -> str:
    text = (prompt or "").strip()
    if not text:
        return f"Complete a typical task with {agent_name or 'the agent'}"
    # First instructive sentence-ish
    for line in text.splitlines():
        line = line.strip(" -*\t")
        if len(line) > 40:
            return line[:200]
    return text[:200]


def slug(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return s or "agent"


def graph_to_meta(graph: AgentGraph | None) -> dict[str, Any]:
    if not graph:
        return {}
    return {
        "agent_graph": graph.model_dump(mode="json"),
    }
