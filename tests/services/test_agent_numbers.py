"""Reading an agent's phone numbers off the platform, and remembering the pick.

A fake stands in for ``httpx.AsyncClient`` so the response shapes each platform
actually returns — including Retell's pre-2026 single-agent field — are pinned
without any network.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from wiretap.services import agent_numbers as svc

AGENT = "agent_abc"


class _Response:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class FakeClient:
    """Records the request and replays a canned body (or an error)."""

    def __init__(self, payload: Any = None, *, error: Exception | None = None) -> None:
        self._payload = payload
        self._error = error
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []

    async def get(self, url: str, headers: dict[str, str] | None = None) -> _Response:
        self.urls.append(url)
        self.headers.append(headers or {})
        if self._error is not None:
            raise self._error
        return _Response(self._payload)


def _discover(client: FakeClient, *, platform: str = "retell", agent_id: str = AGENT):
    return asyncio.run(
        svc.discover_agent_numbers(
            platform=platform, agent_id=agent_id, api_key="key", client=client
        )
    )


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WIRETAP_HOME", str(tmp_path))


def test_retell_marks_the_numbers_routed_to_this_agent() -> None:
    client = FakeClient(
        [
            {
                "phone_number": "+14155550199",
                "nickname": "Support line",
                "inbound_agents": [{"agent_id": "someone_else", "weight": 1}],
            },
            {
                "phone_number": "+14155550123",
                "nickname": "Main line",
                "inbound_agents": [{"agent_id": AGENT, "weight": 1}],
            },
        ]
    )

    numbers = _discover(client)

    assert [(n.number, n.bound) for n in numbers] == [
        ("+14155550123", True),
        ("+14155550199", False),
    ]
    assert numbers[0].label == "Main line"
    assert client.headers[0]["Authorization"] == "Bearer key"


def test_retell_still_reads_the_deprecated_single_agent_field() -> None:
    """Numbers written before the weighted lists landed carry the old shape."""
    client = FakeClient(
        [{"phone_number": "+14155550123", "inbound_agent_id": AGENT}]
    )

    numbers = _discover(client)

    assert [n.bound for n in numbers] == [True]


def test_retell_counts_an_outbound_binding_too() -> None:
    client = FakeClient(
        [
            {
                "phone_number": "+14155550123",
                "outbound_agents": [{"agent_id": AGENT, "weight": 1}],
            }
        ]
    )

    assert _discover(client)[0].bound is True


def test_retell_falls_back_to_the_pretty_number_as_a_label() -> None:
    client = FakeClient(
        [{"phone_number": "+14155550123", "phone_number_pretty": "+1 (415) 555-0123"}]
    )

    assert _discover(client)[0].label == "+1 (415) 555-0123"


def test_vapi_matches_on_the_assistant_id() -> None:
    client = FakeClient(
        [
            {"number": "+14155550199", "name": "Spare", "assistantId": "other"},
            {"number": "+14155550123", "name": "Main", "assistantId": AGENT},
        ]
    )

    numbers = _discover(client, platform="vapi")

    assert [(n.number, n.label, n.bound) for n in numbers] == [
        ("+14155550123", "Main", True),
        ("+14155550199", "Spare", False),
    ]
    assert client.urls == [f"{svc.VAPI_API}/phone-number"]


def test_bound_numbers_sort_first_then_by_number() -> None:
    client = FakeClient(
        [
            {"phone_number": "+14155550123"},
            {"phone_number": "+14155550199"},
            {"phone_number": "+14155550188", "inbound_agent_id": AGENT},
        ]
    )

    # The agent's own number leads even though it sorts last on its own.
    assert [n.number for n in _discover(client)] == [
        "+14155550188",
        "+14155550123",
        "+14155550199",
    ]


def test_undialable_entries_are_dropped() -> None:
    """A BYO SIP trunk entry is not something we can place a call to."""
    client = FakeClient(
        [
            {"number": "sip:agent@example.com", "assistantId": AGENT},
            {"number": "+14155550123", "assistantId": AGENT},
        ]
    )

    assert [n.number for n in _discover(client, platform="vapi")] == ["+14155550123"]


def test_a_platform_without_a_number_api_discovers_nothing() -> None:
    client = FakeClient([{"phone_number": "+14155550123"}])

    assert _discover(client, platform="elevenlabs") == []
    assert client.urls == []


def test_a_missing_api_key_discovers_nothing() -> None:
    result = asyncio.run(
        svc.discover_agent_numbers(
            platform="retell", agent_id=AGENT, api_key="", client=FakeClient([])
        )
    )

    assert result == []


def test_a_failed_request_degrades_to_manual_entry() -> None:
    """Discovery is advisory — the user can always type the number."""
    client = FakeClient(error=httpx.ConnectError("no route"))

    assert _discover(client) == []


def test_an_unexpected_body_discovers_nothing() -> None:
    assert _discover(FakeClient({"error": "nope"})) == []
    assert _discover(FakeClient(["not-a-record"])) == []


def test_the_pick_round_trips_through_the_cache() -> None:
    assert svc.saved_agent_number(platform="retell", agent_id=AGENT) is None

    svc.save_agent_number(" +1 415-555-0123 ", platform="retell", agent_id=AGENT)

    assert svc.saved_agent_number(platform="retell", agent_id=AGENT) == "+14155550123"
    assert svc.settings_path().is_file()


def test_each_agent_remembers_its_own_number() -> None:
    svc.save_agent_number("+14155550123", platform="retell", agent_id=AGENT)
    svc.save_agent_number("+14155550199", platform="vapi", agent_id="other")

    assert svc.saved_agent_number(platform="retell", agent_id=AGENT) == "+14155550123"
    assert svc.saved_agent_number(platform="vapi", agent_id="other") == "+14155550199"
    assert svc.saved_agent_number(platform="retell", agent_id="unknown") is None


def test_the_cache_survives_a_corrupt_file() -> None:
    path = svc.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    assert svc.saved_agent_number(platform="retell", agent_id=AGENT) is None

    svc.save_agent_number("+14155550123", platform="retell", agent_id=AGENT)

    assert svc.saved_agent_number(platform="retell", agent_id=AGENT) == "+14155550123"


def test_the_cache_keeps_unrelated_content() -> None:
    path = svc.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"note": "keep me"}), encoding="utf-8")

    svc.save_agent_number("+14155550123", platform="retell", agent_id=AGENT)

    assert json.loads(path.read_text(encoding="utf-8"))["note"] == "keep me"


def test_an_undialable_number_is_never_cached() -> None:
    with pytest.raises(ValueError, match="E.164"):
        svc.save_agent_number("not-a-number", platform="retell", agent_id=AGENT)

    assert not svc.settings_path().is_file()
