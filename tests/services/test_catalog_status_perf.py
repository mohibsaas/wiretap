"""Catalog / status performance guards."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from wiretap.providers.catalog import litellm_llm_provider_ids
from wiretap.services.onboard import onboard_status


def test_litellm_uses_local_cost_map(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITELLM_LOCAL_MODEL_COST_MAP", raising=False)
    litellm_llm_provider_ids.cache_clear()
    _ = litellm_llm_provider_ids()
    assert os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP") == "True"


def test_onboard_status_can_skip_providers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    status = onboard_status(tmp_path, include_providers=False)
    assert "providers" not in status
    assert status["caller_configured"] is False

    full = onboard_status(tmp_path, include_providers=True)
    assert "providers" in full
    assert "llm" in full["providers"]
