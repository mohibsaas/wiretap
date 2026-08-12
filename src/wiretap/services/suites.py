"""Suite listing / loading for UI and MCP."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from wiretap.config import load_suite
from wiretap.models import SuiteConfig
from wiretap.paths import suite_path, suites_dir


def list_suites(cwd: Path | None = None) -> list[dict[str, Any]]:
    d = suites_dir(cwd)
    if not d.is_dir():
        return []
    out: list[dict[str, Any]] = []
    files = sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml"))
    for fp in files:
        try:
            suite = load_suite(fp)
        except (OSError, ValueError, TypeError, ValidationError) as exc:
            out.append(
                {"name": fp.stem, "path": str(fp), "error": f"invalid suite: {exc}"}
            )
            continue
        out.append(
            {
                "name": fp.stem,
                "path": str(fp),
                "scenario_count": len(suite.scenarios),
                "persona_count": len(suite.personas),
                "platform": suite.agent.platform,
                "transport": suite.agent.transport.value,
            }
        )
    return out


def get_suite(name: str, cwd: Path | None = None) -> SuiteConfig:
    return load_suite(suite_path(name, cwd))


def suite_public_dict(suite: SuiteConfig, *, name: str) -> dict[str, Any]:
    """Serialize suite for API — never include secret values."""
    data = suite.model_dump(mode="json")
    # token_env is an env *name*, not a secret — keep it
    return {"name": name, **data}
