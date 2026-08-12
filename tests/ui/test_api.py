"""API smoke tests for local UI FastAPI app."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wiretap.suite import dump_suite, load_suite
from wiretap.suite.templates import DEFAULT_SUITE
from wiretap.models import JudgeResult, RuleResult, SimulationArtifact
from wiretap.suite import save_simulation
from wiretap.ui.app import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".wiretap" / "suites").mkdir(parents=True)
    suite_path = tmp_path / ".wiretap" / "suites" / "default.yaml"
    suite_path.write_text(DEFAULT_SUITE, encoding="utf-8")
    # Force single-scenario for simple batch start without --all
    suite = load_suite(suite_path)
    suite.scenarios = suite.scenarios[:1]
    dump_suite(suite, suite_path)
    return TestClient(create_app(cwd=tmp_path))


def test_health(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert "version" in body
    assert body["wiretap_root"].endswith(".wiretap")


def test_list_and_get_suite(client: TestClient) -> None:
    res = client.get("/api/suites")
    assert res.status_code == 200
    names = [s["name"] for s in res.json()]
    assert "default" in names
    detail = client.get("/api/suites/default")
    assert detail.status_code == 200
    assert detail.json()["name"] == "default"
    assert "token_env" in detail.json()["agent"] or detail.json()["agent"].get(
        "token_env"
    ) is None


def test_simulations_list_and_get(client: TestClient, tmp_path: Path) -> None:
    art = SimulationArtifact(
        suite_id="default",
        scenario_id="smoke",
        persona_id="priya",
        passed=True,
        transcript=[],
        judge=JudgeResult(passed=True, reason="ok", suggestions=[]),
        rules=RuleResult(passed=True),
    )
    save_simulation(art, tmp_path)
    assert art.simulation_id
    listing = client.get("/api/simulations")
    assert listing.status_code == 200
    assert any(x["simulation_id"] == art.simulation_id for x in listing.json())
    one = client.get(f"/api/simulations/{art.simulation_id}")
    assert one.status_code == 200
    assert one.json()["scenario_id"] == "smoke"


def test_start_batch_returns_id(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_simulate_scenario(suite, scenario, *, suite_id="default", cwd=None):
        return SimulationArtifact(
            suite_id=suite_id,
            scenario_id=scenario.id,
            persona_id=scenario.persona_id,
            passed=True,
            transcript=[],
            judge=JudgeResult(passed=True, reason="ok", suggestions=[]),
            rules=RuleResult(passed=True),
        )

    monkeypatch.setattr(
        "wiretap.services.batches.simulate_scenario", fake_simulate_scenario
    )
    res = client.post("/api/batches", json={"suite": "default", "all": True})
    assert res.status_code == 200
    batch_id = res.json()["batch_id"]
    assert batch_id
    # Allow background task to finish
    import time

    for _ in range(20):
        status = client.get(f"/api/batches/{batch_id}")
        assert status.status_code == 200
        if status.json()["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert status.json()["status"] == "completed"
