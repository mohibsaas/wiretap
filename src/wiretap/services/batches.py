"""In-memory batch orchestration for UI (1..N simulations per Start click)."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from wiretap.suite import load_suite
from wiretap.models import SimulationArtifact, SuiteConfig
from wiretap.paths import suite_path
from wiretap.agent import simulate_scenario
from datetime import UTC, datetime

BatchStatus = Literal["pending", "running", "completed", "failed"]

# Voice dials are slow; never let a single scenario hang the whole batch forever.
DEFAULT_SCENARIO_TIMEOUT_S = 240.0


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class BatchRecord:
    batch_id: str
    suite: str
    status: BatchStatus = "pending"
    scenario_ids: list[str] = field(default_factory=list)
    concurrency: int = 1
    pass_threshold: float = 0.7
    strict: bool = False
    results: list[SimulationArtifact] = field(default_factory=list)
    error: str | None = None
    created_at: str = ""
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
    force_concurrency: bool = False,
    pass_threshold: float = 0.7,
    strict: bool = False,
    agent_id: str | None = None,
    platform: str | None = None,
    token_env: str | None = None,
    agent_from: str | None = None,
    cwd: Path | None = None,
    scenario_timeout_s: float = DEFAULT_SCENARIO_TIMEOUT_S,
) -> BatchRecord:
    from wiretap.suite.agent_override import with_agent_override
    from wiretap.services.onboard import apply_simulator_config
    from wiretap.eval.concurrency import resolve_concurrency

    path = suite_path(suite, cwd)
    cfg = load_suite(path)
    cfg = apply_simulator_config(cfg, cwd)
    cfg = with_agent_override(
        cfg,
        agent_id=agent_id,
        platform=platform,
        token_env=token_env,
        agent_from=agent_from,
        cwd=cwd,
    )
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

    conc, _note = resolve_concurrency(
        concurrency,
        transport=cfg.agent.transport.value,
        platform=cfg.agent.platform,
        force=force_concurrency,
    )

    batch = BatchRecord(
        batch_id=uuid.uuid4().hex,
        suite=path.stem,
        scenario_ids=[s.id for s in selected],
        concurrency=conc,
        pass_threshold=pass_threshold,
        strict=strict,
        created_at=_now_iso(),
    )
    _batches[batch.batch_id] = batch
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as exc:
        raise RuntimeError("start_batch must be called from an async server context") from exc
    loop.create_task(
        _run_batch(
            batch,
            cfg,
            selected,
            path.stem,
            cwd,
            scenario_timeout_s=scenario_timeout_s,
            pass_threshold=pass_threshold,
        )
    )
    return batch


async def _run_batch(
    batch: BatchRecord,
    cfg: SuiteConfig,
    scenarios: list,
    suite_id: str,
    cwd: Path | None,
    *,
    scenario_timeout_s: float = DEFAULT_SCENARIO_TIMEOUT_S,
    pass_threshold: float | None = None,
) -> None:
    threshold = (
        batch.pass_threshold if pass_threshold is None else float(pass_threshold)
    )
    batch.status = "running"
    batch._emit(
        {
            "type": "batch_started",
            "batch_id": batch.batch_id,
            "scenario_count": len(scenarios),
            "concurrency": batch.concurrency,
        }
    )
    sem = asyncio.Semaphore(batch.concurrency)
    failures = 0

    async def one(sc):
        nonlocal failures
        title = sc.name or sc.id
        # Queued = waiting for a concurrency slot (not dialing yet).
        batch._emit(
            {
                "type": "simulation_queued",
                "batch_id": batch.batch_id,
                "scenario_id": sc.id,
                "scenario_name": title,
            }
        )
        async with sem:
            batch._emit(
                {
                    "type": "simulation_started",
                    "batch_id": batch.batch_id,
                    "scenario_id": sc.id,
                    "scenario_name": title,
                }
            )
            try:
                art = await asyncio.wait_for(
                    simulate_scenario(
                        cfg,
                        sc,
                        suite_id=suite_id,
                        batch_id=batch.batch_id,
                        cwd=cwd,
                        pass_threshold=threshold,
                    ),
                    timeout=scenario_timeout_s,
                )
            except TimeoutError:
                failures += 1
                batch._emit(
                    {
                        "type": "simulation_failed",
                        "batch_id": batch.batch_id,
                        "scenario_id": sc.id,
                        "scenario_name": title,
                        "error": (
                            f"Timed out after {int(scenario_timeout_s)}s "
                            "(agent dial / call hung)."
                        ),
                    }
                )
                return None
            except Exception as exc:
                failures += 1
                batch._emit(
                    {
                        "type": "simulation_failed",
                        "batch_id": batch.batch_id,
                        "scenario_id": sc.id,
                        "scenario_name": title,
                        "error": str(exc),
                    }
                )
                return None
            batch.results.append(art)
            batch._emit(
                {
                    "type": "simulation_finished",
                    "batch_id": batch.batch_id,
                    "scenario_id": sc.id,
                    "scenario_name": art.scenario_name or title,
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
                "passed": failures == 0
                and all(a.passed or a.meta.get("inconclusive") for a in batch.results),
                "failures": failures,
                "completed": len(batch.results),
            }
        )
    except Exception as exc:
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
        _persist_evaluation_run(batch, cwd)
        batch.close()


def _persist_evaluation_run(batch: BatchRecord, cwd: Path | None) -> None:
    from wiretap.suite.evaluations import save_evaluation_run

    passed = sum(
        1 for a in batch.results if a.passed and not a.meta.get("inconclusive")
    )
    failed_results = sum(
        1 for a in batch.results if not a.passed and not a.meta.get("inconclusive")
    )
    inconclusive = sum(1 for a in batch.results if a.meta.get("inconclusive"))
    missing = max(0, len(batch.scenario_ids) - len(batch.results))
    try:
        save_evaluation_run(
            {
                "batch_id": batch.batch_id,
                "suite_id": batch.suite,
                "created_at": batch.created_at or _now_iso(),
                "finished_at": _now_iso(),
                "status": batch.status,
                "error": batch.error,
                "scenario_ids": batch.scenario_ids,
                "simulation_ids": [a.simulation_id for a in batch.results],
                "passed": passed,
                "failed": failed_results + missing,
                "inconclusive": inconclusive,
                "total": len(batch.scenario_ids),
                "concurrency": batch.concurrency,
                "pass_threshold": batch.pass_threshold,
            },
            cwd,
        )
    except OSError:
        # Persistence must not crash the live batch UI
        pass


def batch_public(batch: BatchRecord) -> dict[str, Any]:
    return {
        "batch_id": batch.batch_id,
        "suite": batch.suite,
        "status": batch.status,
        "scenario_ids": batch.scenario_ids,
        "concurrency": batch.concurrency,
        "strict": batch.strict,
        "error": batch.error,
        "created_at": batch.created_at,
        "results": [a.model_dump(mode="json") for a in batch.results],
    }
