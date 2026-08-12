"""Config package tests."""

from __future__ import annotations

from pathlib import Path

import yaml

from wiretap.suite import DEFAULT_SUITE, load_suite
from wiretap.models import SuiteConfig


def test_default_suite_parses(tmp_path: Path) -> None:
    p = tmp_path / "default.yaml"
    p.write_text(DEFAULT_SUITE, encoding="utf-8")
    suite = load_suite(p)
    assert isinstance(suite, SuiteConfig)
    assert suite.scenarios[0].beats
    assert suite.personas[0].id == "priya"


def test_suite_roundtrip_yaml() -> None:
    data = yaml.safe_load(DEFAULT_SUITE)
    suite = SuiteConfig.model_validate(data)
    assert suite.agent.transport.value == "text"
