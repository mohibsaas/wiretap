"""wiretap — CLI-first voice agent test simulator.

Public API for library consumers. Prefer the CLI for day-to-day use:

    uv run wiretap init
    uv run wiretap simulate --all
"""

from wiretap.caller import TestAgentOrchestrator, build_orchestrator
from wiretap.config import load_suite
from wiretap.models import (
    Beat,
    Persona,
    Scenario,
    SimulationArtifact,
    SuiteConfig,
)
from wiretap.runner import simulate_scenario

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
