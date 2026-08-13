"""Remote agent list parsing (mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest

from wiretap.importers.remote_agents import list_remote_agents


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


def test_list_retell_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(self, url, **kwargs):  # noqa: ANN001
        assert "list-agents" in url
        return _FakeResp(
            {
                "items": [
                    {"agent_id": "ag_1", "agent_name": "Support"},
                    {"agent_id": "ag_2", "agent_name": "Sales"},
                ]
            }
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    resolved = list_remote_agents("retell", api_key="rk-test")
    assert resolved["source"] == "live"
    assert resolved["agents"][0]["id"] == "ag_1"
    assert "Support" in resolved["agents"][0]["label"]


def test_list_vapi_assistants(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(self, url, **kwargs):  # noqa: ANN001
        assert "vapi.ai" in url
        return _FakeResp([{"id": "asst_1", "name": "Front desk"}])

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    resolved = list_remote_agents("vapi", api_key="vk-test")
    assert resolved["source"] == "live"
    assert resolved["agents"][0]["id"] == "asst_1"


def test_unsupported_platform() -> None:
    resolved = list_remote_agents("livekit", api_key="x")
    assert resolved["live_supported"] is False
    assert resolved["agents"] == []


def test_pick_fallback_non_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    from wiretap.cli import pick as pick_mod

    monkeypatch.setattr(pick_mod, "_can_render_menu", lambda: False)
    monkeypatch.setattr(
        "typer.prompt",
        lambda label, default="": default,
    )
    assert (
        pick_mod.pick_option("LLM provider", ["openai", "anthropic"], default="openai")
        == "openai"
    )
