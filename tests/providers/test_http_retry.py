"""HTTP retry helper for speech providers."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from wiretap.providers.http_retry import with_http_retries


def test_retries_429_then_succeeds() -> None:
    calls = {"n": 0}

    async def _op() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            req = httpx.Request("POST", "https://example.test/stt")
            resp = httpx.Response(429, request=req, headers={"Retry-After": "0"})
            raise httpx.HTTPStatusError("rate limited", request=req, response=resp)
        return "ok"

    out = asyncio.run(with_http_retries(_op, attempts=4, base_delay_s=0.01, label="stt"))
    assert out == "ok"
    assert calls["n"] == 3


def test_does_not_retry_401() -> None:
    async def _op() -> str:
        req = httpx.Request("POST", "https://example.test/stt")
        resp = httpx.Response(401, request=req)
        raise httpx.HTTPStatusError("auth", request=req, response=resp)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(with_http_retries(_op, attempts=3, base_delay_s=0.01))
