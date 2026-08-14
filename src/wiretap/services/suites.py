"""Suite listing / loading for UI and MCP."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from wiretap.suite import dump_suite, load_suite
from wiretap.models import SuiteConfig
from wiretap.paths import suite_path, suites_dir

_SAFE_SUITE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,127}$")


class SuiteCasePatch(BaseModel):
    """One editable row: scenario + linked persona fields."""

    scenario_id: str = Field(min_length=1, max_length=200)
    persona_id: str = Field(min_length=1, max_length=200)
    name: str = Field(default="", max_length=500)
    category: str | None = Field(default=None, max_length=100)
    identity: str = Field(default="", max_length=4000)
    goal: str = Field(default="", max_length=4000)
    constraints: list[str] = Field(default_factory=list, max_length=40)
    max_turns: int = Field(default=20, ge=1, le=200)
    success_criteria: str | None = Field(default=None, max_length=8000)
    rubric: str | None = Field(default=None, max_length=8000)


class UpdateSuiteBody(BaseModel):
    cases: list[SuiteCasePatch] | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, max_length=200)


def validate_suite_name(name: str) -> str:
    """Reject path traversal / odd names before touching the filesystem."""
    raw = (name or "").strip()
    if not raw or "/" in raw or "\\" in raw or raw in {".", ".."}:
        raise ValueError("invalid suite name")
    stem = Path(raw).name
    if stem.endswith((".yaml", ".yml")):
        stem = Path(stem).stem
    if not _SAFE_SUITE_NAME.match(stem):
        raise ValueError("invalid suite name")
    return stem


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
                "title": (suite.title or "").strip() or fp.stem,
                "path": str(fp),
                "scenario_count": len(suite.scenarios),
                "persona_count": len(suite.personas),
                "platform": suite.agent.platform,
                "transport": suite.agent.transport.value,
            }
        )
    return out


def get_suite(name: str, cwd: Path | None = None) -> SuiteConfig:
    return load_suite(suite_path(validate_suite_name(name), cwd))


def suite_public_dict(suite: SuiteConfig, *, name: str) -> dict[str, Any]:
    """Serialize suite for API — never include secret values."""
    data = suite.model_dump(mode="json")
    # token_env is an env *name*, not a secret — keep it
    data["name"] = name
    data["title"] = (suite.title or "").strip() or name
    return data


def update_suite_cases(
    name: str,
    body: UpdateSuiteBody,
    cwd: Path | None = None,
) -> SuiteConfig:
    """Patch suite title and/or scenario + persona fields; preserve agent/models/etc."""
    stem = validate_suite_name(name)
    path = suite_path(stem, cwd)
    suite = load_suite(path)

    if body.title is not None:
        cleaned = body.title.strip()
        if len(cleaned) > 200:
            raise ValueError("title too long")
        suite.title = cleaned

    if body.cases is not None:
        if len(body.cases) < 1:
            raise ValueError("cases must not be empty")
        by_scenario = {c.scenario_id: c for c in body.cases}
        personas_by_id = {p.id: p for p in suite.personas}

        for scenario in suite.scenarios:
            patch = by_scenario.get(scenario.id)
            if not patch:
                continue
            if patch.persona_id != scenario.persona_id:
                raise ValueError(
                    f"persona_id mismatch for scenario {scenario.id!r}: "
                    f"expected {scenario.persona_id!r}"
                )
            scenario.name = patch.name.strip() or scenario.name
            scenario.category = (patch.category or "").strip() or None
            scenario.max_turns = patch.max_turns
            if patch.success_criteria is not None:
                scenario.success_criteria = patch.success_criteria.strip()
            if patch.rubric is not None:
                scenario.rubric = patch.rubric.strip()

            persona = personas_by_id.get(scenario.persona_id)
            if persona is None:
                raise ValueError(f"persona not found: {scenario.persona_id!r}")
            persona.name = patch.name.strip() or persona.name
            persona.identity = patch.identity.strip()
            persona.goal = patch.goal.strip()
            cleaned = [
                c.strip() for c in patch.constraints if isinstance(c, str) and c.strip()
            ]
            if len(cleaned) > 40:
                raise ValueError("too many constraints")
            for item in cleaned:
                if len(item) > 500:
                    raise ValueError("constraint too long")
            persona.constraints = cleaned

    if body.title is None and body.cases is None:
        raise ValueError("nothing to update")

    dump_suite(suite, path)
    return suite


def delete_suite(name: str, cwd: Path | None = None) -> dict[str, Any]:
    """Remove a suite YAML and its agent graph IR, if present."""
    from wiretap.paths import graphs_dir

    stem = validate_suite_name(name)
    path = suite_path(stem, cwd)
    if not path.is_file():
        raise FileNotFoundError(f"Suite not found: {stem}")

    path.unlink()
    removed = [str(path)]

    graph = graphs_dir(cwd) / f"{stem}.graph.json"
    if graph.is_file():
        graph.unlink()
        removed.append(str(graph))

    return {"name": stem, "removed": removed}
