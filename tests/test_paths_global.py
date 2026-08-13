"""wiretap_root resolution — global by default."""

from __future__ import annotations

from pathlib import Path

from wiretap.paths import WIRETAP_HOME_ENV, ensure_layout, wiretap_root
from wiretap.services.secrets import env_file, upsert_secrets


def test_default_root_is_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(WIRETAP_HOME_ENV, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert wiretap_root() == tmp_path / ".wiretap"


def test_wiretap_home_env_override(monkeypatch, tmp_path: Path) -> None:
    custom = tmp_path / "custom-data"
    monkeypatch.setenv(WIRETAP_HOME_ENV, str(custom))
    assert wiretap_root() == custom


def test_explicit_cwd_stays_project_local(tmp_path: Path) -> None:
    assert wiretap_root(tmp_path) == tmp_path / ".wiretap"


def test_ensure_layout_global(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(WIRETAP_HOME_ENV, str(tmp_path / "home"))
    root = ensure_layout()
    assert root == tmp_path / "home"
    assert (root / "suites").is_dir()
    assert (root / "simulations").is_dir()


def test_env_file_follows_global_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(WIRETAP_HOME_ENV, str(tmp_path / "home"))
    assert env_file() == tmp_path / "home" / ".env"
    upsert_secrets({"OPENAI_API_KEY": "sk-global-test"})
    assert (tmp_path / "home" / ".env").is_file()
    text = (tmp_path / "home" / ".env").read_text(encoding="utf-8")
    assert "sk-global-test" in text
