"""Secret store + status attribution."""

from __future__ import annotations

from pathlib import Path

import pytest

from wiretap.services.onboard import onboard_status
from wiretap.services.secrets import key_report, key_status, upsert_secrets


def test_key_report_attributes_project_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RETELL_API_KEY", raising=False)

    # Simulate global home under tmp so primary ≠ project .env
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("WIRETAP_HOME", str(home / ".wiretap"))
    monkeypatch.setenv("HOME", str(home))

    project_env = tmp_path / ".env"
    project_env.write_text(
        "OPENAI_API_KEY=sk-project\nRETELL_API_KEY=retell-project\n",
        encoding="utf-8",
    )

    report = key_report(None)
    assert report["wiretap_env_exists"] is False
    assert report["project_env"] == str(project_env)
    assert report["keys"]["OPENAI_API_KEY"]["set"] is True
    assert report["keys"]["OPENAI_API_KEY"]["sources"] == ["project"]
    assert "wiretap" not in report["keys"]["OPENAI_API_KEY"]["sources"]
    assert key_status(None)["OPENAI_API_KEY"] is True


def test_key_report_reads_legacy_wiretap_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VAPI_API_KEY", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("WIRETAP_HOME", str(home / ".wiretap"))

    legacy = tmp_path / ".wiretap"
    legacy.mkdir()
    (legacy / ".env").write_text("VAPI_API_KEY=vapi-legacy\n", encoding="utf-8")

    report = key_report(None)
    assert report["legacy_env"] == str(legacy / ".env")
    assert report["keys"]["VAPI_API_KEY"]["sources"] == ["legacy"]
    assert key_status(None)["VAPI_API_KEY"] is True


def test_key_report_wiretap_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    upsert_secrets({"OPENAI_API_KEY": "sk-wiretap"}, tmp_path)
    report = key_report(tmp_path)
    assert report["wiretap_env_exists"] is True
    assert report["keys"]["OPENAI_API_KEY"]["sources"] == ["wiretap"]


def test_onboard_status_hides_defaults_when_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    status = onboard_status(tmp_path)
    assert status["caller_configured"] is False
    assert status["caller"]["llm_provider"] is None
    assert status["caller"]["stt"] is None
    assert status["caller"]["tts"] is None
