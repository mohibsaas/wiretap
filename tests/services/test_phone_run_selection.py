"""Choosing web or phone for a dashboard run.

The browser has no prompt to fall back on, so everything the CLI would ask for
has to be resolved up front or refused with instructions.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wiretap.services.agent_numbers import resolve_agent_number, save_agent_number
from wiretap.services.batches import _dial_by_phone
from wiretap.services.twilio_pstn import (
    ACCOUNT_SID_ENV,
    AUTH_TOKEN_ENV,
    FROM_NUMBER_ENV,
    SIP_PASSWORD_ENV,
    save_from_number,
)
from wiretap.suite import dump_suite, load_suite
from wiretap.suite.agent_override import resolve_transport_choice
from wiretap.suite.templates import DEFAULT_SUITE
from wiretap.ui.app import create_app

AGENT_NUMBER = "+14155550111"
CALLER_NUMBER = "+14155550123"


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WIRETAP_HOME", str(tmp_path / ".wiretap"))
    for name in (ACCOUNT_SID_ENV, AUTH_TOKEN_ENV, SIP_PASSWORD_ENV, FROM_NUMBER_ENV):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def suite_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".wiretap" / "suites").mkdir(parents=True)
    path = tmp_path / ".wiretap" / "suites" / "default.yaml"
    path.write_text(DEFAULT_SUITE, encoding="utf-8")
    suite = load_suite(path)
    suite.scenarios = suite.scenarios[:1]
    dump_suite(suite, path)
    return tmp_path


def _make_phone_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wiretap.services.twilio_pstn.missing_pstn_packages", list)
    monkeypatch.setenv(ACCOUNT_SID_ENV, "AC-test-sid")
    monkeypatch.setenv(AUTH_TOKEN_ENV, "test-auth-token")
    save_from_number(CALLER_NUMBER, tmp_path)


def test_web_keeps_the_suite_transport() -> None:
    assert resolve_transport_choice("web", current="text") == "text"
    assert resolve_transport_choice("web", current="pstn") == "webrtc"
    assert resolve_transport_choice("phone", current="text") == "pstn"
    with pytest.raises(ValueError):
        resolve_transport_choice("carrier-pigeon", current="text")


def test_number_resolution_prefers_the_request(suite_dir: Path) -> None:
    suite = load_suite(suite_dir / ".wiretap" / "suites" / "default.yaml")
    assert resolve_agent_number(suite, cwd=suite_dir) == (None, None)

    save_agent_number(
        AGENT_NUMBER,
        platform=suite.agent.platform,
        agent_id=suite.agent.agent_id,
        cwd=suite_dir,
    )
    assert resolve_agent_number(suite, cwd=suite_dir) == (AGENT_NUMBER, "saved")

    suite.agent.phone_number = "+14155550222"
    assert resolve_agent_number(suite, cwd=suite_dir) == ("+14155550222", "suite")
    assert resolve_agent_number(suite, phone="+1 415 555 0333", cwd=suite_dir) == (
        "+14155550333",
        "request",
    )


def test_phone_run_switches_transport_once_ready(
    suite_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_phone_ready(suite_dir, monkeypatch)
    suite = load_suite(suite_dir / ".wiretap" / "suites" / "default.yaml")

    dialing = _dial_by_phone(suite, phone=AGENT_NUMBER, cwd=suite_dir)
    assert dialing.agent.transport.value == "pstn"
    assert dialing.agent.phone_number == AGENT_NUMBER
    # The suite on disk keeps its own transport: phone is a per-run choice.
    assert suite.agent.transport.value != "pstn"


def test_phone_run_refused_before_setup(suite_dir: Path) -> None:
    suite = load_suite(suite_dir / ".wiretap" / "suites" / "default.yaml")
    with pytest.raises(ValueError, match="not set up"):
        _dial_by_phone(suite, phone=AGENT_NUMBER, cwd=suite_dir)


def test_phone_run_refused_without_a_number(
    suite_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_phone_ready(suite_dir, monkeypatch)
    suite = load_suite(suite_dir / ".wiretap" / "suites" / "default.yaml")
    with pytest.raises(ValueError, match="No phone number known"):
        _dial_by_phone(suite, phone=None, cwd=suite_dir)


def test_api_rejects_phone_run_until_configured(suite_dir: Path) -> None:
    client = TestClient(create_app(cwd=suite_dir))
    res = client.post(
        "/api/batches",
        json={"suite": "default", "all": True, "transport": "phone", "phone": AGENT_NUMBER},
    )
    assert res.status_code == 400
    assert "Settings" in res.json()["detail"]


def test_api_reports_the_number_a_phone_run_would_dial(suite_dir: Path) -> None:
    client = TestClient(create_app(cwd=suite_dir))

    empty = client.get("/api/pstn/agent-number", params={"suite": "default"})
    assert empty.status_code == 200
    assert empty.json() == {"number": None, "source": None}

    suite = load_suite(suite_dir / ".wiretap" / "suites" / "default.yaml")
    save_agent_number(
        AGENT_NUMBER,
        platform=suite.agent.platform,
        agent_id=suite.agent.agent_id,
        cwd=suite_dir,
    )
    found = client.get("/api/pstn/agent-number", params={"suite": "default"})
    assert found.json() == {"number": AGENT_NUMBER, "source": "saved"}


def test_api_rejects_unknown_transport(suite_dir: Path) -> None:
    client = TestClient(create_app(cwd=suite_dir))
    res = client.post(
        "/api/batches",
        json={"suite": "default", "all": True, "transport": "carrier-pigeon"},
    )
    assert res.status_code == 400
