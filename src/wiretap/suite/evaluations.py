"""Persisted evaluation runs — one suite execution (parent of scenario sims)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wiretap.models import SimulationArtifact
from wiretap.paths import ensure_layout, evaluations_dir
from wiretap.suite.artifacts import iter_simulations


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def save_evaluation_run(run: dict[str, Any], cwd: Path | None = None) -> Path:
    """Write/overwrite an evaluation run summary under .wiretap/evaluations/."""
    ensure_layout(cwd)
    batch_id = str(run.get("batch_id") or "").strip()
    if not batch_id:
        raise ValueError("evaluation run requires batch_id")
    if not run.get("created_at"):
        run = {**run, "created_at": _now_iso()}
    path = evaluations_dir(cwd) / f"{batch_id}.json"
    path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    return path


def get_evaluation_run(
    batch_id: str, cwd: Path | None = None
) -> dict[str, Any] | None:
    path = evaluations_dir(cwd) / f"{batch_id}.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(data, dict):
            return _enrich_run(data, cwd)
    # Synthesize from simulations tagged with this batch_id
    sims = [
        s
        for s in iter_simulations(cwd, limit=5000)
        if s.batch_id == batch_id
    ]
    if not sims:
        return None
    return _run_from_simulations(batch_id, sims)


def list_evaluation_runs(
    cwd: Path | None = None, limit: int = 40
) -> list[dict[str, Any]]:
    """List parent evaluation runs (newest first)."""
    ensure_layout(cwd)
    by_id: dict[str, dict[str, Any]] = {}

    ev_dir = evaluations_dir(cwd)
    if ev_dir.is_dir():
        for fp in ev_dir.glob("*.json"):
            # Live progress sidecar: {batch_id}.progress.json
            if fp.name.endswith(".progress.json"):
                continue
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or not data.get("batch_id"):
                continue
            by_id[str(data["batch_id"])] = data

    # Include / repair from simulation artifacts (CLI + legacy)
    sims = iter_simulations(cwd, limit=5000)
    grouped: dict[str, list[SimulationArtifact]] = {}
    for s in sims:
        key = s.batch_id or f"legacy:{s.simulation_id}"
        grouped.setdefault(key, []).append(s)

    for key, members in grouped.items():
        if key in by_id:
            # Prefer disk summary but refresh counts from children when present
            by_id[key] = _merge_run(by_id[key], members)
            continue
        by_id[key] = _run_from_simulations(key, members)

    runs = [_enrich_run(r, cwd) for r in by_id.values()]
    runs.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return runs[:limit]


def _run_from_simulations(
    batch_id: str, sims: list[SimulationArtifact]
) -> dict[str, Any]:
    sims_sorted = sorted(sims, key=lambda s: s.created_at or "")
    passed = sum(1 for s in sims if s.passed and not s.meta.get("inconclusive"))
    failed = sum(1 for s in sims if not s.passed and not s.meta.get("inconclusive"))
    inconclusive = sum(1 for s in sims if s.meta.get("inconclusive"))
    return {
        "batch_id": batch_id,
        "suite_id": sims_sorted[0].suite_id if sims_sorted else "",
        "created_at": sims_sorted[0].created_at if sims_sorted else _now_iso(),
        "finished_at": sims_sorted[-1].created_at if sims_sorted else None,
        "status": "completed",
        "scenario_ids": [s.scenario_id for s in sims_sorted],
        "simulation_ids": [s.simulation_id for s in sims_sorted],
        "passed": passed,
        "failed": failed,
        "inconclusive": inconclusive,
        "total": len(sims),
    }


def _merge_run(run: dict[str, Any], sims: list[SimulationArtifact]) -> dict[str, Any]:
    out = dict(run)
    if sims:
        synthesized = _run_from_simulations(str(run.get("batch_id") or ""), sims)
        out["simulation_ids"] = synthesized["simulation_ids"]
        out["passed"] = synthesized["passed"]
        out["failed"] = synthesized["failed"]
        out["inconclusive"] = synthesized["inconclusive"]
        # While a run is live, keep the planned scenario count (not just finished sims).
        if str(out.get("status") or "") in {"running", "pending"}:
            planned = int(out.get("total") or 0) or len(out.get("scenario_ids") or [])
            out["total"] = max(planned, int(synthesized["total"] or 0))
        else:
            out["total"] = synthesized["total"]
        if not out.get("suite_id"):
            out["suite_id"] = synthesized["suite_id"]
    return out


def _enrich_run(run: dict[str, Any], cwd: Path | None) -> dict[str, Any]:
    out = dict(run)
    batch_id = str(out.get("batch_id") or "")
    sims = [
        s.model_dump(mode="json")
        for s in iter_simulations(cwd, limit=5000)
        if s.batch_id == batch_id
        or (not s.batch_id and batch_id == f"legacy:{s.simulation_id}")
    ]
    # Keep lightweight on list; detail endpoint attaches full children
    out.setdefault("total", out.get("total") or len(out.get("simulation_ids") or sims))
    out.setdefault("passed", out.get("passed") or 0)
    out.setdefault("failed", out.get("failed") or 0)
    out.setdefault("inconclusive", out.get("inconclusive") or 0)
    out["_child_count"] = len(sims) or len(out.get("simulation_ids") or [])
    return out


def evaluation_run_detail(
    batch_id: str, cwd: Path | None = None
) -> dict[str, Any] | None:
    run = get_evaluation_run(batch_id, cwd)
    if not run:
        return None
    sims = [
        s
        for s in iter_simulations(cwd, limit=5000)
        if s.batch_id == batch_id
        or (not s.batch_id and batch_id == f"legacy:{s.simulation_id}")
    ]
    sims.sort(key=lambda s: s.created_at or "")
    out = dict(run)
    out["simulations"] = [s.model_dump(mode="json") for s in sims]
    if sims:
        synthesized = _run_from_simulations(batch_id, sims)
        out["passed"] = synthesized["passed"]
        out["failed"] = synthesized["failed"]
        out["inconclusive"] = synthesized["inconclusive"]
        out["total"] = synthesized["total"]
        out["simulation_ids"] = synthesized["simulation_ids"]
    return out


__all__ = [
    "evaluation_run_detail",
    "get_evaluation_run",
    "list_evaluation_runs",
    "save_evaluation_run",
]
