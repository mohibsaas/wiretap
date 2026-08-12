"""Public package API smoke tests."""

from wiretap import (
    SuiteConfig,
    TestAgentOrchestrator,
    __version__,
    build_orchestrator,
    load_suite,
    simulate_scenario,
)


def test_public_exports() -> None:
    assert __version__
    assert TestAgentOrchestrator is not None
    assert callable(build_orchestrator)
    assert SuiteConfig is not None
    assert callable(load_suite)
    assert callable(simulate_scenario)
