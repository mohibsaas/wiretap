"""LiveKit schedule/disconnect helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from wiretap.transport.livekit_util import disconnect_livekit_room, schedule_on_loop


def test_schedule_on_loop_noop_when_closed() -> None:
    loop = asyncio.new_event_loop()
    loop.close()
    called = {"n": 0}

    async def _boom() -> None:
        called["n"] += 1

    schedule_on_loop(loop, _boom)
    assert called["n"] == 0


def test_schedule_on_loop_noop_when_none() -> None:
    async def _boom() -> None:
        raise AssertionError("should not run")

    schedule_on_loop(None, _boom)


def test_disconnect_livekit_room_awaits_disconnect() -> None:
    room = AsyncMock()
    room.disconnect = AsyncMock()

    async def _run() -> None:
        await disconnect_livekit_room(room)
        room.disconnect.assert_awaited()

    asyncio.run(_run())
