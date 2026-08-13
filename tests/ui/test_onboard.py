"""Onboarding + secrets + LLM generator tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wiretap.services.generator import generate_suite, list_categories
from wiretap.services.secrets import key_status, load_dotenv, upsert_secrets
from wiretap.ui.app import create_app


def _fake_llm_tests(count: int, category: str) -> list[dict]:
    out = []
    for i in range(count):
        out.append(
            {
                "name": f"{category.title()} case {i + 1}",
                "identity": f"A caller for {category} scenario {i + 1}",
                "goal": f"Complete {category} goal {i + 1}",
                "say": f"Hello, this is {category} test {i + 1}.",
                "success": f"Agent handles {category} case {i + 1} correctly.",
                "excludes": [],
            }
        )
    return out


def test_categories_catalog_and_generate(monkeypatch: pytest.MonkeyPatch) -> None:
    cats = list_categories()
    ids = {c["id"] for c in cats}
    assert {
        "emotional",
        "linguistic",
        "adversarial",
        "operational",
        "factual",
        "compliance",
        "task",
        "other",
    } <= ids

    def fake_complete(*, model, messages, temperature=0.4, max_tokens=512):
        # Pull count from the user JSON payload
        user = messages[-1]["content"]
        count = 5
        if "Generate exactly" in user:
            # "Generate exactly N test cases"
            try:
                count = int(user.split("Generate exactly ", 1)[1].split(" ", 1)[0])
            except (IndexError, ValueError):
                count = 5
        category = "emotional"
        if '"category": "compliance"' in user or "category 'compliance'" in user:
            category = "compliance"
        elif '"category": "emotional"' in user:
            category = "emotional"
        return json.dumps(_fake_llm_tests(count, category))

    monkeypatch.setattr("wiretap.services.generator.complete", fake_complete)

    suite = generate_suite(
        platform="custom",
        agent_id="x",
        agent_name="X",
        purpose="Cancel flows",
        categories=["emotional", "compliance"],
        tests_per_category=10,
        transport="text",
        model="gpt-4o-mini",
    )
    assert len(suite.scenarios) == 20
    assert all(s.beats for s in suite.scenarios)
    assert {s.category for s in suite.scenarios} == {"emotional", "compliance"}
    assert all(not s.persona_id.endswith("_persona") for s in suite.scenarios)
    assert any(s.name.startswith("Emotional case") for s in suite.scenarios)
    assert any(p.name.startswith("Emotional case") for p in suite.personas)


def test_load_dotenv_fills_environ(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-from-file\n", encoding="utf-8")
    load_dotenv(tmp_path)
    assert os.environ.get("OPENAI_API_KEY") == "sk-from-file"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-shell")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-from-file\n", encoding="utf-8")
    load_dotenv(tmp_path)
    assert os.environ.get("OPENAI_API_KEY") == "sk-shell"  # shell wins


def test_load_dotenv_fills_empty_environ(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-filled\n", encoding="utf-8")
    load_dotenv(tmp_path)
    assert os.environ.get("OPENAI_API_KEY") == "sk-filled"


def test_ui_sees_keys_from_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RETELL_API_KEY", raising=False)
    upsert_secrets(
        {"OPENAI_API_KEY": "sk-ui", "RETELL_API_KEY": "retell-ui"},
        tmp_path,
    )
    # Simulate a process that started before keys existed
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RETELL_API_KEY", raising=False)

    client = TestClient(create_app(cwd=tmp_path))
    res = client.get("/api/onboard/status")
    assert res.status_code == 200
    keys = res.json()["keys"]
    assert keys["OPENAI_API_KEY"] is True
    assert keys["RETELL_API_KEY"] is True
    # Middleware / status path should rehydrate process env for runtime use
    assert os.environ.get("OPENAI_API_KEY") == "sk-ui"

    health = client.get("/api/health").json()
    assert health["secrets_file_exists"] is True
    assert "secrets_file" in health


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


def test_onboard_generate_custom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_complete(*, model, messages, temperature=0.4, max_tokens=512):
        return json.dumps(_fake_llm_tests(3, "compliance"))

    monkeypatch.setattr("wiretap.services.generator.complete", fake_complete)

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
    from wiretap.suite import load_suite
    from wiretap.paths import suite_path

    suite = load_suite(suite_path(body["suite_name"], tmp_path))
    assert suite.models.judge == "gpt-4o-mini"
    assert suite.speech.stt == "pyai"
    assert suite.speech.voice == "nova"
