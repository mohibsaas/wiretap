"""Live TTS voice catalog resolution (mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest

from wiretap.providers.voice_catalog import fetch_tts_voices, resolve_tts_voices


class _FakeResp:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "err", request=httpx.Request("GET", "https://x"), response=httpx.Response(self.status_code)
            )

    def json(self) -> object:
        return self._payload


def test_fetch_elevenlabs_parses_voices(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(self, url, **kwargs):  # noqa: ANN001
        assert "elevenlabs.io" in url
        assert kwargs["headers"]["xi-api-key"] == "el-key"
        return _FakeResp(
            {
                "voices": [
                    {"voice_id": "abc", "name": "Custom Clone"},
                    {"voice_id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel"},
                ]
            }
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    voices, err = fetch_tts_voices("elevenlabs", "el-key")
    assert err is None
    assert voices is not None
    assert voices[0] == {"id": "abc", "label": "Custom Clone"}


def test_fetch_pyai_parses_stock_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(self, url, **kwargs):  # noqa: ANN001
        assert url == "https://api.pyai.com/v1/voices"
        assert kwargs["headers"]["Authorization"] == "Bearer py-key"
        return _FakeResp(
            {
                "object": "list",
                "data": [
                    {"object": "voice", "voice_id": "stock_ava_en_us", "name": "Ava"},
                    {"object": "voice", "voice_id": "stock_dorit_en_us", "name": "Imogen"},
                ],
            }
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    voices, err = fetch_tts_voices("pyai", "py-key")
    assert err is None
    assert voices == [
        {"id": "stock_ava_en_us", "label": "Ava"},
        {"id": "stock_dorit_en_us", "label": "Imogen"},
    ]


def test_resolve_falls_back_to_curated_without_key() -> None:
    resolved = resolve_tts_voices("elevenlabs", api_key=None)
    assert resolved["source"] == "curated"
    assert resolved["live_supported"] is True
    assert any(v["id"] == "21m00Tcm4TlvDq8ikWAM" for v in resolved["voices"])


def test_resolve_uses_live_when_fetch_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "wiretap.providers.voice_catalog.fetch_tts_voices",
        lambda provider, key: ([{"id": "live-1", "label": "Live One"}], None),
    )
    resolved = resolve_tts_voices("pyai", api_key="py-key")
    assert resolved["source"] == "live"
    assert resolved["voices"] == [{"id": "live-1", "label": "Live One"}]
    assert resolved["default_voice"] == "live-1"


def test_resolve_reports_error_code_on_fetch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "wiretap.providers.voice_catalog.fetch_tts_voices",
        lambda provider, key: (None, "http_401"),
    )
    resolved = resolve_tts_voices("pyai", api_key="bad-key")
    assert resolved["source"] == "curated"
    assert resolved["error"] == "http_401"


def test_openai_has_no_live_fetch() -> None:
    resolved = resolve_tts_voices("openai", api_key="sk-test")
    assert resolved["source"] == "curated"
    assert resolved["live_supported"] is False
