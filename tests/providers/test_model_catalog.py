"""Live LLM model catalog resolution (mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest

from wiretap.providers.model_catalog import fetch_llm_models, resolve_llm_models


class _FakeResp:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "err",
                request=httpx.Request("GET", "https://x"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> object:
        return self._payload


def test_fetch_openai_filters_non_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(self, url, **kwargs):  # noqa: ANN001
        assert "api.openai.com" in url
        return _FakeResp(
            {
                "data": [
                    {"id": "gpt-4o-mini"},
                    {"id": "gpt-4o"},
                    {"id": "whisper-1"},
                    {"id": "dall-e-3"},
                    {"id": "text-embedding-3-small"},
                ]
            }
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    models, err = fetch_llm_models("openai", "sk-test")
    assert err is None
    assert models is not None
    assert "gpt-4o-mini" in models
    assert "gpt-4o" in models
    assert "whisper-1" not in models
    assert "dall-e-3" not in models


def test_resolve_live_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "wiretap.providers.model_catalog.fetch_llm_models",
        lambda provider, key: (["gpt-4o-mini", "gpt-4o", "o4-mini"], None),
    )
    resolved = resolve_llm_models("openai", api_key="sk-test")
    assert resolved["source"] == "live"
    assert resolved["models"][0] == "gpt-4o-mini"
    assert "gpt-4o" in resolved["models"]


def test_resolve_curated_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "wiretap.providers.model_catalog.api_key_for_llm",
        lambda provider, cwd=None: None,
    )
    resolved = resolve_llm_models("openai", api_key=None)
    assert resolved["source"] == "curated"
    assert "gpt-4o-mini" in resolved["models"]


def test_resolve_reports_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "wiretap.providers.model_catalog.fetch_llm_models",
        lambda provider, key: (None, "http_401"),
    )
    resolved = resolve_llm_models("openai", api_key="bad")
    assert resolved["source"] == "curated"
    assert resolved["error"] == "http_401"
