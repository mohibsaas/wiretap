"""wiretap — CLI-first voice agent test simulator.

Public API for library consumers. Prefer the CLI for day-to-day use:

    uvx wiretap init
    uvx wiretap simulate --all
"""

from wiretap.caller import Caller
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

# Aliases
RunArtifact = SimulationArtifact
run_scenario = simulate_scenario

__all__ = [
    "Beat",
    "Caller",
    "Persona",
    "RunArtifact",
    "Scenario",
    "SimulationArtifact",
    "SuiteConfig",
    "__version__",
    "load_suite",
    "run_scenario",
    "simulate_scenario",
]
