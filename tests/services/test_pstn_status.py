"""Phone-testing readiness, shared by `wiretap status` and the dashboard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wiretap.services.twilio_pstn import (
    ACCOUNT_SID_ENV,
    AUTH_TOKEN_ENV,
    FROM_NUMBER_ENV,
    SIP_PASSWORD_ENV,
    pstn_status,
    save_from_number,
)
from wiretap.ui.app import create_app

SECRET_VALUES = ("AC-test-sid", "test-auth-token")


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep Twilio vars out of the process env — teardown restores whatever was there."""
    monkeypatch.setenv("WIRETAP_HOME", str(tmp_path / ".wiretap"))
    for name in (ACCOUNT_SID_ENV, AUTH_TOKEN_ENV, SIP_PASSWORD_ENV, FROM_NUMBER_ENV):
        monkeypatch.delenv(name, raising=False)


def test_status_reports_each_missing_step(tmp_path: Path) -> None:
    status = pstn_status(tmp_path)
    assert status["ready"] is False
    assert status["has_credentials"] is False
    assert status["from_number"] is None
    assert "Twilio keys" in status["missing"]
    assert "caller number" in status["missing"]


def test_status_flags_absent_extra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "wiretap.services.twilio_pstn.missing_pstn_packages", lambda: ["pyVoIP"]
    )
    status = pstn_status(tmp_path)
    assert status["extra_installed"] is False
    assert status["missing_packages"] == ["pyVoIP"]
    assert "uv sync --extra pstn" in status["missing"]


def test_ready_once_credentials_and_number_are_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("wiretap.services.twilio_pstn.missing_pstn_packages", list)
    monkeypatch.setenv(ACCOUNT_SID_ENV, SECRET_VALUES[0])
    monkeypatch.setenv(AUTH_TOKEN_ENV, SECRET_VALUES[1])
    save_from_number("+14155550123", tmp_path)

    status = pstn_status(tmp_path)
    assert status["ready"] is True
    assert status["missing"] == []
    assert status["from_number"] == "+14155550123"
    assert status["keys"][ACCOUNT_SID_ENV] is True
    # Presence only: a credential value must never travel with the status.
    assert not any(secret in json.dumps(status) for secret in SECRET_VALUES)


def test_api_reports_status_without_returning_values(tmp_path: Path) -> None:
    client = TestClient(create_app(cwd=tmp_path))

    first = client.get("/api/pstn/status")
    assert first.status_code == 200
    assert first.json()["has_credentials"] is False

    saved = client.post(
        "/api/secrets",
        json={"secrets": {ACCOUNT_SID_ENV: SECRET_VALUES[0], AUTH_TOKEN_ENV: SECRET_VALUES[1]}},
    )
    assert saved.status_code == 200
    assert sorted(saved.json()["updated"]) == sorted([ACCOUNT_SID_ENV, AUTH_TOKEN_ENV])
    assert not any(secret in saved.text for secret in SECRET_VALUES)

    picked = client.post("/api/twilio/from-number", json={"from_number": "+14155550123"})
    assert picked.status_code == 200
    assert picked.json()["selected"] == "+14155550123"

    after = client.get("/api/pstn/status")
    body = after.json()
    assert body["has_credentials"] is True
    assert body["from_number"] == "+14155550123"
    assert not any(secret in after.text for secret in SECRET_VALUES)


def test_api_rejects_unmanaged_keys(tmp_path: Path) -> None:
    client = TestClient(create_app(cwd=tmp_path))
    res = client.post("/api/secrets", json={"secrets": {"SHELL": "/bin/sh"}})
    assert res.status_code == 400
