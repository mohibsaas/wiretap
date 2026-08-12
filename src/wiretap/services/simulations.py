"""Simulation artifact queries."""

from __future__ import annotations

from pathlib import Path

from wiretap.models import SimulationArtifact
from wiretap.store import get_simulation, iter_simulations


def list_simulations(cwd: Path | None = None, limit: int = 50) -> list[SimulationArtifact]:
    return list(reversed(iter_simulations(cwd, limit=limit)))


def get_simulation_detail(
    simulation_id: str, cwd: Path | None = None
) -> SimulationArtifact | None:
    return get_simulation(simulation_id, cwd)
