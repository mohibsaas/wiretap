"""Public package API smoke tests."""

from wiretap import (
    Caller,
    SuiteConfig,
    __version__,
    load_suite,
    simulate_scenario,
)


def test_public_exports() -> None:
    assert __version__
    assert Caller is not None
    assert SuiteConfig is not None
    assert callable(load_suite)
    assert callable(simulate_scenario)
