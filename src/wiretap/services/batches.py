"""In-memory batch orchestration for UI (1..N simulations per Start click)."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from wiretap.config import load_suite
from wiretap.models import SimulationArtifact, SuiteConfig
from wiretap.paths import suite_path
from wiretap.runner import simulate_scenario

BatchStatus = Literal["pending", "running", "completed", "failed"]


@dataclass
class BatchRecord:
    batch_id: str
    suite: str
    status: BatchStatus = "pending"
    scenario_ids: list[str] = field(default_factory=list)
    concurrency: int = 1
    strict: bool = False
    results: list[SimulationArtifact] = field(default_factory=list)
    error: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    _subscribers: list[asyncio.Queue[dict[str, Any] | None]] = field(default_factory=list)

    def subscribe(self) -> asyncio.Queue[dict[str, Any] | None]:
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._subscribers.append(q)
        for ev in self.events:
            q.put_nowait(ev)
        if self.status in {"completed", "failed"}:
            q.put_nowait(None)
        return q

    def _emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        for q in self._subscribers:
            q.put_nowait(event)

    def close(self) -> None:
        for q in self._subscribers:
            q.put_nowait(None)


_batches: dict[str, BatchRecord] = {}


def get_batch(batch_id: str) -> BatchRecord | None:
    return _batches.get(batch_id)


def start_batch(
    *,
    suite: str,
    all_scenarios: bool = False,
    scenario_id: str | None = None,
    concurrency: int = 1,
    strict: bool = False,
    cwd: Path | None = None,
) -> BatchRecord:
    path = suite_path(suite, cwd)
    cfg = load_suite(path)
    if strict:
        cfg.mode.strict = True
        cfg.mode.temperature = 0.2

    selected = cfg.scenarios
    if scenario_id:
        selected = [s for s in cfg.scenarios if s.id == scenario_id]
        if not selected:
            raise KeyError(f"No scenario {scenario_id!r}")
    elif not all_scenarios and len(cfg.scenarios) > 1:
        raise ValueError("Pass all_scenarios=True or scenario_id for multi-scenario suites")

    batch = BatchRecord(
        batch_id=uuid.uuid4().hex,
        suite=path.stem,
        scenario_ids=[s.id for s in selected],
        concurrency=max(1, concurrency),
        strict=strict,
    )
    _batches[batch.batch_id] = batch
    asyncio.create_task(_run_batch(batch, cfg, selected, path.stem, cwd))
    return batch


async def _run_batch(
    batch: BatchRecord,
    cfg: SuiteConfig,
    scenarios: list,
    suite_id: str,
    cwd: Path | None,
) -> None:
    batch.status = "running"
    batch._emit({"type": "batch_started", "batch_id": batch.batch_id})
    sem = asyncio.Semaphore(batch.concurrency)

    async def one(sc):
        async with sem:
            batch._emit(
                {
                    "type": "simulation_started",
                    "batch_id": batch.batch_id,
                    "scenario_id": sc.id,
                }
            )
            try:
                art = await simulate_scenario(cfg, sc, suite_id=suite_id, cwd=cwd)
            except (RuntimeError, ValueError, KeyError, OSError) as exc:
                batch._emit(
                    {
                        "type": "simulation_failed",
                        "batch_id": batch.batch_id,
                        "scenario_id": sc.id,
                        "error": str(exc),
                    }
                )
                raise
            batch.results.append(art)
            batch._emit(
                {
                    "type": "simulation_finished",
                    "batch_id": batch.batch_id,
                    "scenario_id": sc.id,
                    "simulation_id": art.simulation_id,
                    "passed": art.passed,
                    "inconclusive": bool(art.meta.get("inconclusive")),
                    "reason": art.judge.reason[:200],
                }
            )
            return art

    try:
        await asyncio.gather(*[one(sc) for sc in scenarios])
        batch.status = "completed"
        batch._emit(
            {
                "type": "batch_completed",
                "batch_id": batch.batch_id,
                "passed": all(
                    a.passed or a.meta.get("inconclusive") for a in batch.results
                ),
            }
        )
    except (RuntimeError, ValueError, KeyError, OSError) as exc:
        batch.status = "failed"
        batch.error = str(exc)
        batch._emit(
            {
                "type": "batch_failed",
                "batch_id": batch.batch_id,
                "error": str(exc),
            }
        )
    finally:
        batch.close()


def batch_public(batch: BatchRecord) -> dict[str, Any]:
    return {
        "batch_id": batch.batch_id,
        "suite": batch.suite,
        "status": batch.status,
        "scenario_ids": batch.scenario_ids,
        "concurrency": batch.concurrency,
        "strict": batch.strict,
        "error": batch.error,
        "results": [a.model_dump(mode="json") for a in batch.results],
    }
