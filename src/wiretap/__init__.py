"""wiretap — CLI-first voice agent test simulator.

Public API for library consumers. Prefer the CLI for day-to-day use:

    uv run wiretap init
    uv run wiretap simulate --all
"""

from wiretap.agent import TestAgentOrchestrator, build_orchestrator, simulate_scenario
from wiretap.models import (
    Beat,
    Persona,
    Scenario,
    SimulationArtifact,
    SuiteConfig,
)
from wiretap.suite import load_suite

__version__ = "0.1.0"

__all__ = [
    "Beat",
    "Persona",
    "Scenario",
    "SimulationArtifact",
    "SuiteConfig",
    "TestAgentOrchestrator",
    "__version__",
    "build_orchestrator",
    "load_suite",
    "simulate_scenario",
]
