"""CLI init / status / ensure helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from wiretap.cli.main import app
from wiretap.cli.prompts import ensure_env_key, ensure_platform_key
from wiretap.services.secrets import key_status, upsert_secrets


@pytest.fixture()
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.chdir(tmp_path)
    return CliRunner()


def test_status_empty(runner: CliRunner) -> None:
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "not configured" in result.output.lower() or "Test agent" in result.output


def test_init_non_interactive_exits(runner: CliRunner) -> None:
    # CliRunner is non-TTY by default
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 1
    assert "interactive" in result.output.lower()


def test_ensure_env_key_via_arg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ensure_env_key("OPENAI_API_KEY", cwd=tmp_path, api_key="sk-test-from-arg")
    assert key_status(tmp_path)["OPENAI_API_KEY"] is True
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "sk-test-from-arg" in env_text


def test_ensure_platform_key_retell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    ensure_platform_key("retell", cwd=tmp_path, api_key="retell-test-key")
    assert key_status(tmp_path)["RETELL_API_KEY"] is True


def test_ensure_env_key_skips_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    upsert_secrets({"VAPI_API_KEY": "already"}, tmp_path)
    # Should not raise even non-interactive when already set
    assert ensure_env_key("VAPI_API_KEY", cwd=tmp_path) is True


def test_import_help_shows_api_key(runner: CliRunner) -> None:
    result = runner.invoke(app, ["import", "retell", "--help"])
    assert result.exit_code == 0
    assert "--api-key" in result.output


def test_help_lists_init_status(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.output
    assert "status" in result.output
