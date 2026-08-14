"""Suite listing / loading for UI and MCP."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from wiretap.importers.suite_builder import slug
from wiretap.models import (
    AgentTarget,
    Beat,
    ModelSlots,
    Persona,
    Scenario,
    SpeechConfig,
    SuiteConfig,
    TransportKind,
)
from wiretap.paths import ensure_layout, graphs_dir, suite_path, suites_dir
from wiretap.prompts.defaults import (
    DEFAULT_CALLER_OPENING,
    DEFAULT_GENERATED_RUBRIC,
    DEFAULT_PERSONA_PERSONALITY,
    DEFAULT_SUCCESS_CRITERIA,
    DO_NOT_REVEAL_TEST_BOT,
)
from wiretap.suite import dump_suite, load_suite

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


class CreateSuiteBody(BaseModel):
    """Create a blank suite (add cases later) or name a generated suite."""

    name: str = Field(min_length=1, max_length=128)
    title: str = Field(default="", max_length=200)
    agent_from: str | None = Field(default=None, max_length=128)


class AddSuiteCaseBody(BaseModel):
    name: str = Field(default="New test case", max_length=500)
    category: str | None = Field(default=None, max_length=100)
    identity: str = Field(default="", max_length=4000)
    goal: str = Field(default="", max_length=4000)
    constraints: list[str] = Field(default_factory=list, max_length=40)
    max_turns: int = Field(default=20, ge=1, le=200)
    success_criteria: str = Field(default="", max_length=8000)
    rubric: str = Field(default="", max_length=8000)
    opening: str = Field(default="", max_length=2000)


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


def save_suite(name: str, suite: SuiteConfig, cwd: Path | None = None) -> Path:
    """Write a suite under the data dir. Writes nothing to stdout."""
    stem = validate_suite_name(name)
    ensure_layout(cwd)
    path = suite_path(stem, cwd)
    dump_suite(suite, path)
    return path


def save_suite_import(
    name: str,
    suite: SuiteConfig,
    graph: Any,
    cwd: Path | None = None,
) -> dict[str, str]:
    """Persist an imported suite + AgentGraph IR. Writes nothing to stdout.

    Shared by the CLI importer and MCP so neither can be talked into writing
    outside the data directory.
    """
    stem = validate_suite_name(name)
    path = save_suite(stem, suite, cwd)
    ir_path = graphs_dir(cwd) / f"{stem}.graph.json"
    ir_path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    return {"name": stem, "suite_path": str(path), "graph_path": str(ir_path)}


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


def _unique_id(base: str, seen: set[str], *, limit: int = 48) -> str:
    root = slug(base)[:limit] or "item"
    out = root
    n = 2
    while out in seen:
        out = f"{root}_{n}"
        n += 1
    seen.add(out)
    return out


def _agent_target_for_new_suite(
    *,
    agent_from: str | None,
    cwd: Path | None,
) -> AgentTarget:
    """Prefer an existing suite's agent, then onboard state, else a text stub."""
    from wiretap.services.onboard import load_onboard_state

    if agent_from and agent_from.strip():
        src_stem = validate_suite_name(agent_from)
        src_path = suite_path(src_stem, cwd)
        if src_path.is_file():
            src = load_suite(src_path)
            return src.agent.model_copy(deep=True)

    state = load_onboard_state(cwd)
    plat = (state.get("platform") or "").strip().lower()
    agent_id = state.get("agent_id")
    if plat and plat != "custom":
        return AgentTarget(
            transport=TransportKind.WEBRTC,
            platform=plat,
            agent_id=str(agent_id) if agent_id else None,
            token_env=None,
        )
    return AgentTarget(transport=TransportKind.TEXT, platform=None, agent_id=None)


def _apply_caller_defaults(suite: SuiteConfig, cwd: Path | None) -> None:
    from wiretap.services.onboard import load_onboard_state

    state = load_onboard_state(cwd)
    if state.get("simulator_model"):
        suite.models.simulator = str(state["simulator_model"])
    if state.get("judge_model"):
        suite.models.judge = str(state["judge_model"])
    if state.get("stt"):
        suite.speech.stt = str(state["stt"])
    if state.get("tts"):
        suite.speech.tts = str(state["tts"])
    if state.get("voice"):
        suite.speech.voice = state.get("voice")


def create_blank_suite(
    *,
    name: str,
    title: str = "",
    agent_from: str | None = None,
    cwd: Path | None = None,
) -> SuiteConfig:
    """Create an empty suite YAML so cases can be added one by one in the UI."""
    stem = validate_suite_name(name)
    ensure_layout(cwd)
    path = suite_path(stem, cwd)
    if path.is_file():
        raise ValueError(f"suite already exists: {stem}")

    display = (title or "").strip() or stem
    suite = SuiteConfig(
        title=display,
        agent=_agent_target_for_new_suite(agent_from=agent_from, cwd=cwd),
        models=ModelSlots(),
        speech=SpeechConfig(),
        personas=[],
        scenarios=[],
    )
    _apply_caller_defaults(suite, cwd)
    dump_suite(suite, path)
    return suite


def add_suite_case(
    name: str,
    body: AddSuiteCaseBody,
    cwd: Path | None = None,
) -> SuiteConfig:
    """Append one persona + scenario pair to a suite."""
    stem = validate_suite_name(name)
    path = suite_path(stem, cwd)
    suite = load_suite(path)

    seen_scenarios = {s.id for s in suite.scenarios}
    seen_personas = {p.id for p in suite.personas}
    label = (body.name or "").strip() or "New test case"
    scenario_id = _unique_id(label, seen_scenarios)
    persona_id = _unique_id(f"{label}_caller", seen_personas)

    constraints = [
        c.strip() for c in body.constraints if isinstance(c, str) and c.strip()
    ]
    if not constraints:
        constraints = [DO_NOT_REVEAL_TEST_BOT]
    if len(constraints) > 40:
        raise ValueError("too many constraints")

    opening = (body.opening or "").strip() or DEFAULT_CALLER_OPENING
    suite.personas.append(
        Persona(
            id=persona_id,
            name=label,
            identity=(body.identity or "").strip()
            or "A caller exercising this suite",
            goal=(body.goal or "").strip() or "Complete the stated task",
            personality=DEFAULT_PERSONA_PERSONALITY,
            constraints=constraints,
        )
    )
    suite.scenarios.append(
        Scenario(
            id=scenario_id,
            name=label,
            persona_id=persona_id,
            category=(body.category or "").strip() or None,
            max_turns=body.max_turns,
            success_criteria=(body.success_criteria or "").strip()
            or DEFAULT_SUCCESS_CRITERIA,
            rubric=(body.rubric or "").strip() or DEFAULT_GENERATED_RUBRIC,
            beats=[Beat(at_turn=1, say=opening)],
        )
    )
    dump_suite(suite, path)
    return suite
