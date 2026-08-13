"""Capture status and retry behavior of the dispatcher."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from wiretap.models import AgentTarget
from wiretap.toolcalls import (
    CAPTURE_ERROR,
    CAPTURE_OK,
    CAPTURE_UNSUPPORTED,
    collect_tool_calls,
)
from wiretap.transport.base import CallRef

TARGET = AgentTarget(platform="retell", token_env="RETELL_API_KEY")


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETELL_API_KEY", "test-key")
    monkeypatch.setattr("wiretap.services.secrets.load_dotenv", lambda *a, **k: None)


def _response(status: int) -> httpx.Response:
    request = httpx.Request("GET", "https://api.retellai.com/v2/get-call/x")
    return httpx.Response(status, request=request)


def test_no_call_ref_is_unsupported_not_error() -> None:
    """The text stub has no backend to ask — that is not a failure."""
    records, capture = asyncio.run(collect_tool_calls(None, TARGET))

    assert records == []
    assert capture == CAPTURE_UNSUPPORTED


def test_unknown_platform_is_unsupported() -> None:
    ref = CallRef(platform="synthflow", call_id="c1")

    _, capture = asyncio.run(collect_tool_calls(ref, TARGET))

    assert capture == CAPTURE_UNSUPPORTED


def test_permanent_auth_failure_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key that cannot read calls will not start being able to mid-run."""
    attempts = 0

    async def fetch(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        raise httpx.HTTPStatusError("403", request=None, response=_response(403))

    monkeypatch.setattr("wiretap.toolcalls.retell.fetch_call", fetch)
    ref = CallRef(platform="retell", call_id="c1")

    records, capture = asyncio.run(collect_tool_calls(ref, TARGET))

    assert capture == CAPTURE_ERROR
    assert records == []
    assert attempts == 1, "403 must fail fast rather than sleeping between retries"


def test_transient_failure_is_retried_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool calls land only after the record finalizes, so a gap is expected."""
    attempts = 0

    async def fetch(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.HTTPStatusError("404", request=None, response=_response(404))
        return {
            "call_status": "ended",
            "transcript_with_tool_calls": [
                {
                    "role": "tool_call_invocation",
                    "tool_call_id": "t1",
                    "name": "check_current_date",
                    "arguments": "",
                },
                {
                    "role": "tool_call_result",
                    "tool_call_id": "t1",
                    "content": "2026-08-13",
                    "successful": True,
                },
            ],
        }

    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("wiretap.toolcalls.retell.fetch_call", fetch)
    ref = CallRef(platform="retell", call_id="c1")

    records, capture = asyncio.run(
        collect_tool_calls(ref, TARGET, sleep=sleep)
    )

    assert capture == CAPTURE_OK
    assert [r.name for r in records] == ["check_current_date"]
    assert attempts == 2
    assert slept, "a not-yet-final record should back off before retrying"


def test_missing_key_reports_error_without_calling_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RETELL_API_KEY", raising=False)

    async def fetch(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("must not reach the network without a key")

    monkeypatch.setattr("wiretap.toolcalls.retell.fetch_call", fetch)
    ref = CallRef(platform="retell", call_id="c1")

    _, capture = asyncio.run(collect_tool_calls(ref, TARGET))

    assert capture == CAPTURE_ERROR


def test_empty_arguments_string_parses_to_empty_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retell sends "" for tools whose extraction happens server-side."""

    async def fetch(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "call_status": "ended",
            "transcript_with_tool_calls": [
                {
                    "role": "tool_call_invocation",
                    "tool_call_id": "t1",
                    "name": "extract_update_dynamic_variable",
                    "arguments": "",
                }
            ],
        }

    monkeypatch.setattr("wiretap.toolcalls.retell.fetch_call", fetch)
    ref = CallRef(platform="retell", call_id="c1")

    records, capture = asyncio.run(collect_tool_calls(ref, TARGET))

    assert capture == CAPTURE_OK
    assert records[0].arguments == {}
