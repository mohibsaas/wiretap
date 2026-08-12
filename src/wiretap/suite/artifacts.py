"""Persist simulation artifacts under .wiretap/simulations/."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from wiretap.models import SimulationArtifact
from wiretap.paths import ensure_layout, simulation_artifact_dirs, simulations_dir


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_ids(
    artifact: SimulationArtifact, *, raw_line: str | None = None
) -> SimulationArtifact:
    data = artifact.model_dump()
    if not data.get("simulation_id"):
        if raw_line:
            data["simulation_id"] = hashlib.sha256(raw_line.encode()).hexdigest()[:16]
        else:
            data["simulation_id"] = uuid.uuid4().hex
    if not data.get("created_at"):
        data["created_at"] = _now_iso()
    return SimulationArtifact.model_validate(data)


def save_simulation(artifact: SimulationArtifact, cwd: Path | None = None) -> Path:
    ensure_layout(cwd)
    art = _ensure_ids(artifact)
    artifact.simulation_id = art.simulation_id
    artifact.created_at = art.created_at
    day = datetime.now(UTC).strftime("%Y%m%d")
    path = simulations_dir(cwd) / f"{day}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(art.model_dump_json() + "\n")
    return path


def iter_simulations(cwd: Path | None = None, limit: int = 50) -> list[SimulationArtifact]:
    out: list[SimulationArtifact] = []
    seen: set[str] = set()
    for directory in simulation_artifact_dirs(cwd):
        for fp in sorted(directory.glob("*.jsonl")):
            for line in fp.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                art = _ensure_ids(
                    SimulationArtifact.model_validate(json.loads(line)),
                    raw_line=line,
                )
                if art.simulation_id in seen:
                    continue
                seen.add(art.simulation_id)
                out.append(art)
    return out[-limit:]


def get_simulation(
    simulation_id: str, cwd: Path | None = None
) -> SimulationArtifact | None:
    for art in iter_simulations(cwd, limit=5000):
        if art.simulation_id == simulation_id:
            return art
    return None


def latest_baseline(
    scenario_id: str, cwd: Path | None = None
) -> SimulationArtifact | None:
    sims = [
        r for r in iter_simulations(cwd, limit=500) if r.scenario_id == scenario_id
    ]
    return sims[-1] if sims else None


def regression_failed(
    current: SimulationArtifact, baseline: SimulationArtifact | None
) -> bool:
    return bool(baseline and baseline.passed and not current.passed)


__all__ = [
    "get_simulation",
    "iter_simulations",
    "latest_baseline",
    "regression_failed",
    "save_simulation",
]
