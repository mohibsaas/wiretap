"""Live evaluation progress on disk — shared by CLI and UI.

Written under ``.wiretap/evaluations/{batch_id}.progress.json`` while a run is
active so the local UI can poll the same state the CLI Rich board sees, even
when the run was started outside the UI process.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wiretap.paths import ensure_layout, evaluations_dir

ACTIVE_STATUSES = frozenset({"pending", "running"})


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def progress_path(batch_id: str, cwd: Path | None = None) -> Path:
    return evaluations_dir(cwd) / f"{batch_id}.progress.json"


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(raw)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def start_run_progress(
    *,
    batch_id: str,
    suite_id: str,
    scenarios: list[tuple[str, str]],
    concurrency: int = 1,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Create the progress file and a running evaluation stub for list UIs."""
    ensure_layout(cwd)
    now = _now_iso()
    progress: dict[str, Any] = {
        "batch_id": batch_id,
        "suite_id": suite_id,
        "status": "running",
        "created_at": now,
        "updated_at": now,
        "concurrency": concurrency,
        "scenarios": [
            {
                "scenario_id": sid,
                "scenario_name": sname or sid,
                "phase": "queued",
                "detail": "waiting for slot",
                "turn": 0,
                "simulation_id": None,
                "passed": None,
                "inconclusive": None,
                "error": None,
            }
            for sid, sname in scenarios
        ],
    }
    write_run_progress(progress, cwd)
    # Stub evaluation so Simulations lists the run while it is live.
    try:
        from wiretap.suite.evaluations import save_evaluation_run

        save_evaluation_run(
            {
                "batch_id": batch_id,
                "suite_id": suite_id,
                "created_at": now,
                "finished_at": None,
                "status": "running",
                "scenario_ids": [sid for sid, _ in scenarios],
                "simulation_ids": [],
                "passed": 0,
                "failed": 0,
                "inconclusive": 0,
                "total": len(scenarios),
                "concurrency": concurrency,
            },
            cwd,
        )
    except OSError:
        pass
    return progress


def write_run_progress(progress: dict[str, Any], cwd: Path | None = None) -> Path:
    batch_id = str(progress.get("batch_id") or "").strip()
    if not batch_id:
        raise ValueError("progress requires batch_id")
    progress = {**progress, "updated_at": _now_iso()}
    path = progress_path(batch_id, cwd)
    _atomic_write(path, progress)
    return path


def read_run_progress(
    batch_id: str, cwd: Path | None = None
) -> dict[str, Any] | None:
    path = progress_path(batch_id, cwd)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def list_run_progress(
    cwd: Path | None = None, *, active_only: bool = True
) -> list[dict[str, Any]]:
    ensure_layout(cwd)
    out: list[dict[str, Any]] = []
    root = evaluations_dir(cwd)
    if not root.is_dir():
        return out
    for fp in root.glob("*.progress.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not data.get("batch_id"):
            continue
        if active_only and str(data.get("status") or "") not in ACTIVE_STATUSES:
            continue
        out.append(data)
    out.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""), reverse=True)
    return out


def apply_sim_event(
    progress: dict[str, Any],
    *,
    scenario_id: str,
    phase: str,
    detail: str = "",
    turn: int = 0,
    scenario_name: str | None = None,
    simulation_id: str | None = None,
    passed: bool | None = None,
    inconclusive: bool | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Mutate a progress dict from a SimEvent / batch SSE-style update."""
    rows = list(progress.get("scenarios") or [])
    found = False
    for row in rows:
        if str(row.get("scenario_id")) != scenario_id:
            continue
        found = True
        row["phase"] = phase
        if detail:
            row["detail"] = detail
        if turn:
            row["turn"] = turn
        if scenario_name:
            row["scenario_name"] = scenario_name
        if simulation_id:
            row["simulation_id"] = simulation_id
        if passed is not None:
            row["passed"] = passed
        if inconclusive is not None:
            row["inconclusive"] = inconclusive
        if error is not None:
            row["error"] = error
        break
    if not found:
        rows.append(
            {
                "scenario_id": scenario_id,
                "scenario_name": scenario_name or scenario_id,
                "phase": phase,
                "detail": detail,
                "turn": turn,
                "simulation_id": simulation_id,
                "passed": passed,
                "inconclusive": inconclusive,
                "error": error,
            }
        )
    progress["scenarios"] = rows
    return progress


def touch_scenario(
    batch_id: str,
    *,
    scenario_id: str,
    phase: str,
    detail: str = "",
    turn: int = 0,
    scenario_name: str | None = None,
    simulation_id: str | None = None,
    passed: bool | None = None,
    inconclusive: bool | None = None,
    error: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any] | None:
    progress = read_run_progress(batch_id, cwd)
    if not progress:
        return None
    apply_sim_event(
        progress,
        scenario_id=scenario_id,
        phase=phase,
        detail=detail,
        turn=turn,
        scenario_name=scenario_name,
        simulation_id=simulation_id,
        passed=passed,
        inconclusive=inconclusive,
        error=error,
    )
    try:
        write_run_progress(progress, cwd)
    except OSError:
        return progress
    return progress


def finish_run_progress(
    batch_id: str,
    *,
    status: str = "completed",
    cwd: Path | None = None,
) -> None:
    """Mark progress done and remove the live file (final eval JSON remains)."""
    progress = read_run_progress(batch_id, cwd)
    if progress:
        progress["status"] = status
        try:
            write_run_progress(progress, cwd)
        except OSError:
            pass
    path = progress_path(batch_id, cwd)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def progress_public(progress: dict[str, Any]) -> dict[str, Any]:
    scenarios = progress.get("scenarios") or []
    done = sum(
        1
        for s in scenarios
        if str(s.get("phase") or "") in {"finished", "failed"}
    )
    return {
        "batch_id": progress.get("batch_id"),
        "suite_id": progress.get("suite_id"),
        "status": progress.get("status"),
        "created_at": progress.get("created_at"),
        "updated_at": progress.get("updated_at"),
        "concurrency": progress.get("concurrency"),
        "total": len(scenarios),
        "done": done,
        "scenarios": scenarios,
    }
