"""Helpers for LiveKit room lifecycle (Retell + generic LiveKit transports)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any


def schedule_on_loop(
    loop: asyncio.AbstractEventLoop | None,
    factory: Callable[[], Coroutine[Any, Any, Any]],
) -> None:
    """Thread-safe schedule; no-op if the loop is closed (Ctrl+C shutdown)."""
    if loop is None:
        return
    try:
        if loop.is_closed() or not loop.is_running():
            return
    except Exception:
        return

    def _run() -> None:
        try:
            if loop.is_closed():
                return
            asyncio.ensure_future(factory(), loop=loop)
        except RuntimeError:
            # Event loop closed between check and schedule.
            return

    try:
        loop.call_soon_threadsafe(_run)
    except RuntimeError:
        return


async def disconnect_livekit_room(room: object | None) -> None:
    """Disconnect a LiveKit room even when the caller task is being cancelled.

    LiveKit's FFI keeps posting to the asyncio loop after connect. If we close
    the loop (Ctrl+C) without disconnecting first, it spam-logs
    ``error putting to queue: Event loop is closed``.
    """
    if room is None:
        return
    disconnect = getattr(room, "disconnect", None)
    if not callable(disconnect):
        return
    try:
        await asyncio.shield(asyncio.wait_for(disconnect(), timeout=3.0))
    except (TimeoutError, asyncio.CancelledError, Exception):
        try:
            # Best-effort second shot without wait_for wrapping.
            await asyncio.shield(disconnect())
        except Exception:
            pass
