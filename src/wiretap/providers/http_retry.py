"""Retry transient speech-provider HTTP failures (429 / 5xx).

Never logs response bodies — they can contain account details.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

T = TypeVar("T")

# Statuses worth a short backoff before failing the turn.
_RETRYABLE = frozenset({408, 429, 500, 502, 503, 504})


async def with_http_retries(
    op: Callable[[], Awaitable[T]],
    *,
    attempts: int = 4,
    base_delay_s: float = 0.6,
    label: str = "speech",
) -> T:
    """Run ``op``; retry on rate-limit / transient HTTP errors."""
    last: BaseException | None = None
    for i in range(max(1, attempts)):
        try:
            return await op()
        except httpx.HTTPStatusError as exc:
            last = exc
            code = int(exc.response.status_code)
            if code not in _RETRYABLE or i >= attempts - 1:
                raise
            retry_after = exc.response.headers.get("Retry-After")
            delay = base_delay_s * (2**i)
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    pass
            await asyncio.sleep(min(delay, 12.0))
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last = exc
            if i >= attempts - 1:
                raise
            await asyncio.sleep(min(base_delay_s * (2**i), 12.0))
    assert last is not None
    raise RuntimeError(f"{label} failed after retries") from last


__all__ = ["with_http_retries"]
