"""Tool implementations behind the wiretap MCP server.

Free of any ``mcp`` import so behavior stays testable without the optional
extra, and so the FastMCP wrapper in ``server.py`` is pure registration.

Two rules hold for everything here:

* Names that reach the filesystem go through ``validate_suite_name`` — MCP
  arguments are model-supplied and must never be able to escape the data dir.
* Nothing may write to stdout, which carries the MCP JSON-RPC stream.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import inspect
import json
import sys
import uuid

import httpx
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from wiretap.models import SimulationArtifact, SuiteConfig

MAX_LIMIT = 200
DEFAULT_CONCURRENCY = 4
MAX_CONCURRENCY = 8
SCENARIO_TIMEOUT_S = 900.0

# Remote importers sharing the async ``(agent_id) -> (suite, graph)`` shape.
IMPORT_PLATFORMS = ("vapi", "retell", "bland", "bolna", "elevenlabs", "synthflow")


class ToolError(Exception):
    """Bad tool input — reported to the calling agent, not a crash."""


@contextlib.contextmanager
def _quiet() -> Iterator[None]:
    """Divert stray library prints to stderr, away from the JSON-RPC stream."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


def _json(payload: Any) -> str:
    return json.dumps(payload, default=str)


def _tool(fn: Callable[..., Any]) -> Callable[..., str]:
    """Serialize to JSON and turn expected failures into an error payload.

    FastMCP derives its schema from the signature, so keep the parameters
    intact while correcting the return type to what the wrapper actually
    hands back. Setting ``__signature__`` is what makes this stick —
    ``inspect.signature`` otherwise follows ``__wrapped__`` back to ``fn``.

    ``RuntimeError`` is included because that is how the provider layer
    reports a missing API key, which is user error rather than a crash.
    ``httpx.HTTPError`` covers upstream platform failures (404s, timeouts,
    connection errors) so they stay in-band instead of surfacing as
    framework-level tool errors.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return _json(fn(*args, **kwargs))
        except (
            ToolError,
            ValueError,
            FileNotFoundError,
            RuntimeError,
            httpx.HTTPError,
        ) as exc:
            return _json({"error": str(exc)})

    wrapper.__signature__ = inspect.signature(fn).replace(return_annotation=str)
    wrapper.__annotations__ = {**fn.__annotations__, "return": str}
    return wrapper


def _validated(name: str) -> str:
    from wiretap.services.suites import validate_suite_name

    try:
        return validate_suite_name(name)
    except ValueError as exc:
        raise ToolError(f"Invalid suite name {name!r}: {exc}") from None


def _limit(value: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, MAX_LIMIT))


def _truncate(text: str, limit: int = 400) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _summary(art: SimulationArtifact) -> dict[str, Any]:
    """Compact view of a simulation — no transcript bodies.

    Full transcripts blow out an agent's context; ``get_simulation`` serves
    them on demand.
    """
    return {
        "simulation_id": art.simulation_id,
        "batch_id": art.batch_id,
        "created_at": art.created_at,
        "suite_id": art.suite_id,
        "scenario_id": art.scenario_id,
        "scenario_name": art.scenario_name,
        "persona_id": art.persona_id,
        "passed": art.passed,
        "inconclusive": bool(art.meta.get("inconclusive")),
        "verdict": art.judge.verdict,
        "score": art.judge.score,
        "reason": _truncate(art.judge.reason),
        "suggestions": art.judge.suggestions[:5],
        "turns": len(art.transcript),
        "tool_calls": [tc.name for tc in art.tool_calls],
        "rule_failures": art.rules.failures[:10],
        "rule_errors": art.rules.errors[:10],
    }


# --------------------------------------------------------------------------
# Suites
# --------------------------------------------------------------------------


@_tool
def list_suites() -> list[dict[str, Any]]:
    """List local suites with scenario / persona counts and target platform."""
    from wiretap.services.suites import list_suites as _list

    return _list()


@_tool
def get_suite(name: str) -> dict[str, Any]:
    """Get one suite as JSON — agent target, models, personas, scenarios."""
    from wiretap.services.suites import get_suite as _get
    from wiretap.services.suites import suite_public_dict

    stem = _validated(name)
    return suite_public_dict(_get(stem), name=stem)


@_tool
def export_suite(name: str) -> dict[str, Any]:
    """Return a suite's YAML in a ``{"name", "yaml"}`` JSON envelope, ready to commit to git or CI."""
    from wiretap.services.suites import get_suite as _get
    from wiretap.suite import suite_to_yaml

    stem = _validated(name)
    return {"name": stem, "yaml": suite_to_yaml(_get(stem))}


# --------------------------------------------------------------------------
# Simulations and evaluations
# --------------------------------------------------------------------------


@_tool
def list_simulations(limit: int = 20) -> list[dict[str, Any]]:
    """Recent simulation summaries, newest first."""
    from wiretap.services.simulations import list_simulations as _list

    return [_summary(a) for a in _list(limit=_limit(limit, 20))]


@_tool
def latest_simulations(limit: int = 10) -> list[dict[str, Any]]:
    """Recent simulation summaries (alias of list_simulations)."""
    from wiretap.services.simulations import list_simulations as _list

    return [_summary(a) for a in _list(limit=_limit(limit, 10))]


@_tool
def get_simulation(simulation_id: str) -> dict[str, Any]:
    """Full simulation detail including the transcript."""
    from wiretap.services.simulations import get_simulation_detail

    art = get_simulation_detail((simulation_id or "").strip())
    if art is None:
        raise ToolError(f"No simulation with id {simulation_id!r}")
    return art.model_dump(mode="json")


@_tool
def list_evaluations(limit: int = 20) -> list[dict[str, Any]]:
    """List evaluation runs (batches) newest first, with pass/fail counts."""
    from wiretap.suite.evaluations import list_evaluation_runs

    runs = list_evaluation_runs(limit=_limit(limit, 20))
    return [{k: v for k, v in r.items() if k != "simulations"} for r in runs]


@_tool
def get_evaluation(batch_id: str) -> dict[str, Any]:
    """One evaluation run with its child simulation summaries."""
    from wiretap.suite.evaluations import evaluation_run_detail

    run = evaluation_run_detail((batch_id or "").strip())
    if run is None:
        raise ToolError(f"No evaluation run with batch_id {batch_id!r}")
    sims = run.get("simulations")
    if isinstance(sims, list):
        from wiretap.models import SimulationArtifact

        run = dict(run)
        run["simulations"] = [
            _summary(SimulationArtifact.model_validate(s))
            for s in sims
            if isinstance(s, dict)
        ]
    return run


@_tool
def list_categories() -> list[dict[str, Any]]:
    """Scenario categories available to suite generation."""
    from wiretap.services import generator

    return generator.list_categories()


# --------------------------------------------------------------------------
# Simulate
# --------------------------------------------------------------------------


@_tool
def simulate_suite(
    suite: str = "default",
    scenario: str | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> dict[str, Any]:
    """Simulate a suite (or one scenario) against the live agent.

    Returns per-scenario summaries; fetch transcripts with get_simulation.
    """
    from wiretap.agent import simulate_scenario
    from wiretap.services.suites import get_suite as _get

    stem = _validated(suite)
    cfg = _get(stem)

    selected = list(cfg.scenarios)
    if scenario:
        wanted = scenario.strip()
        selected = [s for s in cfg.scenarios if s.id == wanted]
        if not selected:
            available = ", ".join(s.id for s in cfg.scenarios) or "none"
            raise ToolError(
                f"No scenario {wanted!r} in suite {stem!r}. Available: {available}"
            )
    if not selected:
        raise ToolError(f"Suite {stem!r} has no scenarios.")

    batch_id = uuid.uuid4().hex[:12]
    slots = max(1, min(int(concurrency or DEFAULT_CONCURRENCY), MAX_CONCURRENCY))

    async def _run() -> list[Any]:
        sem = asyncio.Semaphore(slots)

        async def one(sc: Any) -> Any:
            async with sem:
                return await asyncio.wait_for(
                    simulate_scenario(cfg, sc, suite_id=stem, batch_id=batch_id),
                    timeout=SCENARIO_TIMEOUT_S,
                )

        return await asyncio.gather(
            *(one(sc) for sc in selected), return_exceptions=True
        )

    with _quiet():
        results = asyncio.run(_run())

    sims: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for sc, result in zip(selected, results, strict=True):
        if isinstance(result, BaseException):
            detail = (
                f"timed out after {int(SCENARIO_TIMEOUT_S)}s"
                if isinstance(result, TimeoutError)
                else str(result)
            )
            errors.append({"scenario_id": sc.id, "error": detail})
            continue
        sims.append(_summary(result))

    return {
        "batch_id": batch_id,
        "suite": stem,
        "total": len(selected),
        "passed": sum(1 for s in sims if s["passed"] and not s["inconclusive"]),
        "failed": sum(1 for s in sims if not s["passed"] and not s["inconclusive"]),
        "inconclusive": sum(1 for s in sims if s["inconclusive"]),
        "errored": len(errors),
        "simulations": sims,
        "errors": errors,
    }


# --------------------------------------------------------------------------
# Generate and import
# --------------------------------------------------------------------------


@_tool
def generate_suite(
    name: str,
    platform: str = "custom",
    agent_id: str | None = None,
    agent_name: str = "agent",
    purpose: str = "",
    categories: str | None = None,
    tests_per_category: int = 3,
    transport: str = "webrtc",
) -> dict[str, Any]:
    """LLM-generate a new suite of scenarios and save it locally."""
    from wiretap.services import generator
    from wiretap.services.suites import save_suite

    stem = _validated(name)
    cats = generator.parse_categories(categories)
    with _quiet():
        suite = generator.generate_suite(
            platform=platform,
            agent_id=agent_id,
            agent_name=agent_name,
            purpose=purpose,
            categories=cats,
            tests_per_category=_limit(tests_per_category, 3),
            transport=transport,
        )
        path = save_suite(stem, suite)
    return _saved_suite(stem, suite, path)


@_tool
def fill_suite_scenarios(
    name: str,
    categories: str | None = None,
    tests_per_category: int = 3,
    purpose: str = "",
) -> dict[str, Any]:
    """Regenerate personas / scenarios on an existing suite, keeping its target."""
    from wiretap.services import generator
    from wiretap.services.suites import get_suite as _get
    from wiretap.services.suites import save_suite

    stem = _validated(name)
    existing = _get(stem)
    cats = generator.parse_categories(categories)
    with _quiet():
        suite = generator.fill_suite_scenarios(
            existing,
            categories=cats,
            tests_per_category=_limit(tests_per_category, 3),
            purpose=purpose,
            agent_name=existing.agent.platform or "agent",
        )
        path = save_suite(stem, suite)
    return _saved_suite(stem, suite, path)


@_tool
def import_agent(platform: str, agent_id: str, name: str = "") -> dict[str, Any]:
    """Import a live agent (vapi, retell, bland, bolna, elevenlabs, synthflow)."""
    from wiretap import importers
    from wiretap.services.suites import save_suite_import

    key = (platform or "").strip().lower()
    if key not in IMPORT_PLATFORMS:
        raise ToolError(
            f"Unknown platform {platform!r}. Choose from: {', '.join(IMPORT_PLATFORMS)}"
        )
    agent = (agent_id or "").strip()
    if not agent:
        raise ToolError("agent_id is required")

    fetch = {
        "vapi": importers.import_vapi_assistant,
        "retell": importers.import_retell_agent,
        "bland": importers.import_bland_pathway,
        "bolna": importers.import_bolna_agent,
        "elevenlabs": importers.import_elevenlabs_agent,
        "synthflow": importers.import_synthflow_agent,
    }[key]

    stem = _validated(name.strip() or key)
    with _quiet():
        suite, graph = asyncio.run(fetch(agent))
        saved = save_suite_import(stem, suite, graph)
    return {**saved, **_suite_shape(suite)}


@_tool
def import_livekit_agent(
    room_name: str,
    room_url: str,
    name: str = "livekit",
    agent_name: str | None = None,
) -> dict[str, Any]:
    """Build a suite targeting a LiveKit room + agent worker."""
    from wiretap.importers import suite_for_livekit_agent
    from wiretap.services.suites import save_suite_import

    if not (room_name or "").strip() or not (room_url or "").strip():
        raise ToolError("room_name and room_url are required")

    stem = _validated(name)
    with _quiet():
        suite, graph = suite_for_livekit_agent(
            room_name=room_name.strip(),
            room_url=room_url.strip(),
            agent_name=agent_name,
        )
        saved = save_suite_import(stem, suite, graph)
    return {**saved, **_suite_shape(suite)}


def _suite_shape(suite: SuiteConfig) -> dict[str, Any]:
    return {
        "scenario_count": len(suite.scenarios),
        "persona_count": len(suite.personas),
        "scenarios": [
            {"id": s.id, "name": s.name, "category": s.category} for s in suite.scenarios
        ],
    }


def _saved_suite(stem: str, suite: SuiteConfig, path: Any) -> dict[str, Any]:
    return {"name": stem, "suite_path": str(path), **_suite_shape(suite)}


TOOLS: tuple[Callable[..., str], ...] = (
    list_suites,
    get_suite,
    export_suite,
    list_simulations,
    latest_simulations,
    get_simulation,
    list_evaluations,
    get_evaluation,
    list_categories,
    simulate_suite,
    generate_suite,
    fill_suite_scenarios,
    import_agent,
    import_livekit_agent,
)

__all__ = ["IMPORT_PLATFORMS", "TOOLS", "ToolError"] + [f.__name__ for f in TOOLS]
