"""Build a SuiteConfig (+ optional AgentGraph) from imported platform text."""

from __future__ import annotations

import re

from wiretap.importers.agent_graph import AgentGraph
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
from wiretap.prompts.defaults import (
    DEFAULT_CALLER_OPENING,
    DO_NOT_REVEAL_TEST_BOT,
    FLOW_COVERAGE_OPENING,
    FLOW_COVERAGE_RUBRIC,
    IMPORTED_PERSONA_PERSONALITY,
    IMPORTED_SMOKE_RUBRIC,
)
from wiretap.prompts.caller_knowledge import enrich_persona_knowledge


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
        name=f"Caller for {agent_name}" if agent_name else "Imported caller",
        identity=f"A customer calling {agent_name or 'the agent'}",
        goal=goal,
        personality=IMPORTED_PERSONA_PERSONALITY,
        constraints=[DO_NOT_REVEAL_TEST_BOT],
        knowledge=enrich_persona_knowledge({}),
    )
    beats: list[Beat] = [
        Beat(at_turn=1, say=first_message.strip() or DEFAULT_CALLER_OPENING),
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
            rubric=IMPORTED_SMOKE_RUBRIC,
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
                    "Test agent progresses through the agent's main flow; "
                    f"known nodes: {', '.join(graph.node_ids()[:8])}"
                ),
                rubric=FLOW_COVERAGE_RUBRIC,
                beats=[Beat(at_turn=1, say=FLOW_COVERAGE_OPENING)],
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


def first_instructive_line(prompt: str, *, limit: int = 200) -> str:
    """First line substantial enough to read as an instruction. '' when none."""
    text = (prompt or "").strip()
    if not text:
        return ""
    for line in text.splitlines():
        line = line.strip(" -*\t")
        if len(line) > 40:
            return line[:limit]
    return text[:limit]


def _guess_goal(prompt: str, agent_name: str) -> str:
    line = first_instructive_line(prompt)
    if not line:
        return f"Complete a typical task with {agent_name or 'the agent'}"
    return line


def slug(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return s or "agent"
