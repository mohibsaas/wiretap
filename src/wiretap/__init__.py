"""wiretap — CLI-first voice agent test simulator.

Public API for library consumers. Prefer the CLI for day-to-day use:

    wiretap import vapi --assistant-id asst_xxx
    wiretap simulate --all
"""

from __future__ import annotations

from typing import Any

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


def __getattr__(name: str) -> Any:
    # Lazy exports so `import wiretap` / CLI --help stay fast (no LiteLLM).
    if name in {
        "Beat",
        "Persona",
        "Scenario",
        "SimulationArtifact",
        "SuiteConfig",
    }:
        from wiretap import models as _models

        return getattr(_models, name)
    if name in {"TestAgentOrchestrator", "build_orchestrator", "simulate_scenario"}:
        from wiretap import agent as _agent

        return getattr(_agent, name)
    if name == "load_suite":
        from wiretap.suite import load_suite

        return load_suite
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
