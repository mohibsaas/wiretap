"""Onboarding + secrets + generator tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wiretap.services.generator import generate_suite, list_categories
from wiretap.services.secrets import key_status, upsert_secrets
from wiretap.ui.app import create_app


def test_categories_max_ten() -> None:
    cats = list_categories()
    assert any(c["id"] == "emotional" for c in cats)
    assert any(c["id"] == "compliance" for c in cats)
    suite = generate_suite(
        platform="custom",
        agent_id="x",
        agent_name="X",
        purpose="Cancel flows",
        categories=["emotional", "compliance"],
        tests_per_category=10,
        transport="text",
    )
    assert len(suite.scenarios) == 20
    assert all(s.beats for s in suite.scenarios)


def test_upsert_secrets_never_echoes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    updated = upsert_secrets({"OPENAI_API_KEY": "sk-test-secret"}, tmp_path)
    assert updated == ["OPENAI_API_KEY"]
    status = key_status(tmp_path)
    assert status["OPENAI_API_KEY"] is True
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "sk-test-secret" in env_text
    # API status must not include the value
    client = TestClient(create_app(cwd=tmp_path))
    res = client.get("/api/secrets/status")
    assert res.status_code == 200
    assert res.json()["OPENAI_API_KEY"] is True
    assert "sk-test-secret" not in res.text


def test_onboard_generate_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(cwd=tmp_path))
    caller = client.post(
        "/api/onboard/caller",
        json={
            "llm_provider": "openai",
            "llm_api_key": "sk-test-caller",
            "simulator_model": "gpt-4o-mini",
            "judge_model": "gpt-4o-mini",
            "stt": "pyai",
            "tts": "pyai",
            "voice": "nova",
            "stt_api_key": "pyai-test-key",
        },
    )
    assert caller.status_code == 200
    assert "sk-test-caller" not in caller.text
    assert "pyai-test-key" not in caller.text
    providers = client.get("/api/providers")
    assert providers.status_code == 200
    assert providers.json()["llm"][0]["id"] == "openai"
    assert "pyai" not in {p["id"] for p in providers.json()["llm"]}
    assert providers.json()["stt"][0]["id"] == "pyai"
    assert providers.json()["tts"][0]["id"] == "pyai"
    assert any(p["id"] == "deepgram" for p in providers.json()["stt"])
    assert any(p["id"] == "cartesia" for p in providers.json()["tts"])
    conn = client.post(
        "/api/onboard/connect",
        json={"platform": "custom", "agent_id": "demo"},
    )
    assert conn.status_code == 200
    gen = client.post(
        "/api/onboard/generate",
        json={
            "purpose": "Support cancellations",
            "categories": ["compliance"],
            "tests_per_category": 3,
        },
    )
    assert gen.status_code == 200
    body = gen.json()
    assert body["scenario_count"] == 3
    status = client.get("/api/onboard/status")
    assert status.json()["completed"] is True
    assert status.json()["caller"]["stt"] == "pyai"
    assert status.json()["caller"]["voice"] == "nova"
    suites = client.get("/api/suites")
    assert any(s["name"] == body["suite_name"] for s in suites.json())
    agents = client.get("/api/agents")
    assert agents.status_code == 200
    # Suite YAML got caller stack applied
    from wiretap.config import load_suite
    from wiretap.paths import suite_path

    suite = load_suite(suite_path(body["suite_name"], tmp_path))
    assert suite.models.judge == "gpt-4o-mini"
    assert suite.speech.stt == "pyai"
    assert suite.speech.voice == "nova"