"""Test-agent package — orchestrator + simulate entrypoints."""

from wiretap.agent.beats import beat_for_turn
from wiretap.agent.events import ProgressHandler, SimEvent, truncate
from wiretap.agent.orchestrator import (
    FlowNode,
    TestAgentOrchestrator,
    build_orchestrator,
    phases_to_nodes,
)
from wiretap.agent.simulate import simulate_scenario

__all__ = [
    "FlowNode",
    "ProgressHandler",
    "SimEvent",
    "TestAgentOrchestrator",
    "beat_for_turn",
    "build_orchestrator",
    "phases_to_nodes",
    "simulate_scenario",
    "truncate",
]
