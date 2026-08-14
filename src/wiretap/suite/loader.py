"""Load and dump suite YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

from wiretap.models import SuiteConfig


def load_suite(path: Path | str) -> SuiteConfig:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Suite not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"Suite must be a mapping: {p}")
    return SuiteConfig.model_validate(data)


def suite_to_yaml(suite: SuiteConfig) -> str:
    return yaml.safe_dump(suite.model_dump(mode="json"), sort_keys=False)


def dump_suite(suite: SuiteConfig, path: Path | str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(suite_to_yaml(suite), encoding="utf-8")
