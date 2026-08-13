"""Agent turn gate — silence endpointing + STT (provider-agnostic)."""

from __future__ import annotations

import asyncio
import struct

from wiretap.transport.base import Inbound
from wiretap.transport.transcript_util import looks_incomplete_utterance
from wiretap.transport.turn_gate import (
    AgentTurnGate,
    pcm16_rms,
    receive_coalesced,
)


def _tone(samples: int, *, amplitude: int = 4000) -> bytes:
    out = bytearray()
    for i in range(samples):
        v = amplitude if (i // 20) % 2 == 0 else -amplitude
        out.extend(struct.pack("<h", v))
    return bytes(out)


def _silence(samples: int) -> bytes:
    return b"\x00\x00" * samples


def test_pcm16_rms_silence_is_zero() -> None:
    assert pcm16_rms(_silence(100)) == 0.0
    assert pcm16_rms(_tone(100)) > 350


def test_looks_incomplete_utterance() -> None:
    assert looks_incomplete_utterance("I understand how frustrating")
    assert looks_incomplete_utterance("I'll make sure your request for an")
    assert not looks_incomplete_utterance(
        "Are you reaching out about a new concrete project?"
    )
    assert not looks_incomplete_utterance(
        "I want to make sure your information goes to the right person"
    )


def test_gate_emits_one_utterance_after_silence(monkeypatch) -> None:
    uttered: list[str] = []

    class _FakeSTT:
        async def transcribe(self, audio):  # noqa: ANN001
            assert len(audio.pcm) >= 8_000
            return "Hello, thanks for calling."

    monkeypatch.setattr(
        "wiretap.transport.turn_gate.build_stt",
        lambda _name: _FakeSTT(),
    )

    async def _run() -> None:
        gate = AgentTurnGate(
            silence_s=0.15,
            poll_s=0.05,
            min_speech_bytes=8_000,
            on_utterance=lambda t: uttered.append(t),
        )
        await gate.start()
        try:
            gate.push(_tone(5_000), sample_rate=16_000)
            await asyncio.sleep(0.05)
            gate.push(_tone(5_000), sample_rate=16_000)
            await asyncio.sleep(0.35)
            assert uttered == ["Hello, thanks for calling."]
            gate.push(_tone(5_000), sample_rate=16_000)
            await asyncio.sleep(0.35)
            assert uttered == ["Hello, thanks for calling."]
        finally:
            await gate.stop()

    asyncio.run(_run())


def test_gate_waits_through_mid_utterance_pause(monkeypatch) -> None:
    uttered: list[str] = []
    calls = {"n": 0}

    class _FakeSTT:
        async def transcribe(self, audio):  # noqa: ANN001
            calls["n"] += 1
            return "Full sentence after a breath."

    monkeypatch.setattr(
        "wiretap.transport.turn_gate.build_stt",
        lambda _name: _FakeSTT(),
    )

    async def _run() -> None:
        gate = AgentTurnGate(
            silence_s=0.25,
            poll_s=0.05,
            min_speech_bytes=4_000,
            on_utterance=lambda t: uttered.append(t),
        )
        await gate.start()
        try:
            gate.push(_tone(3_000), sample_rate=16_000)
            await asyncio.sleep(0.1)
            gate.push(_tone(3_000), sample_rate=16_000)
            await asyncio.sleep(0.4)
            assert uttered == ["Full sentence after a breath."]
            assert calls["n"] == 1
        finally:
            await gate.stop()

    asyncio.run(_run())


def test_gate_mute_drops_audio(monkeypatch) -> None:
    uttered: list[str] = []

    class _FakeSTT:
        async def transcribe(self, audio):  # noqa: ANN001
            return "Hello, thanks for waiting."

    monkeypatch.setattr(
        "wiretap.transport.turn_gate.build_stt",
        lambda _name: _FakeSTT(),
    )

    async def _run() -> None:
        gate = AgentTurnGate(
            silence_s=0.1,
            poll_s=0.05,
            min_speech_bytes=2_000,
            on_utterance=lambda t: uttered.append(t),
        )
        await gate.start()
        try:
            gate.mute()
            gate.push(_tone(8_000), sample_rate=16_000)
            await asyncio.sleep(0.25)
            assert uttered == []
            gate.unmute(clear=True)
            gate.push(_tone(8_000), sample_rate=16_000)
            await asyncio.sleep(0.3)
            assert uttered == ["Hello, thanks for waiting."]
        finally:
            await gate.stop()

    asyncio.run(_run())


def test_gate_ignores_low_energy_noise(monkeypatch) -> None:
    uttered: list[str] = []

    class _FakeSTT:
        async def transcribe(self, audio):  # noqa: ANN001
            return "should not fire"

    monkeypatch.setattr(
        "wiretap.transport.turn_gate.build_stt",
        lambda _name: _FakeSTT(),
    )

    async def _run() -> None:
        gate = AgentTurnGate(
            silence_s=0.1,
            poll_s=0.05,
            energy_threshold=350,
            on_utterance=lambda t: uttered.append(t),
        )
        await gate.start()
        try:
            gate.push(_tone(8_000, amplitude=50), sample_rate=16_000)
            await asyncio.sleep(0.25)
            assert uttered == []
        finally:
            await gate.stop()

    asyncio.run(_run())


def test_gate_survives_stt_errors(monkeypatch) -> None:
    """STT 429/blips must not kill the poll loop forever."""
    uttered: list[str] = []
    calls = {"n": 0}

    class _FlakySTT:
        async def transcribe(self, audio):  # noqa: ANN001
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("429 Too Many Requests")
            return "Still here after the rate limit."

    monkeypatch.setattr(
        "wiretap.transport.turn_gate.build_stt",
        lambda _name: _FlakySTT(),
    )

    async def _run() -> None:
        gate = AgentTurnGate(
            silence_s=0.1,
            poll_s=0.05,
            min_speech_bytes=2_000,
            on_utterance=lambda t: uttered.append(t),
        )
        await gate.start()
        try:
            gate.push(_tone(8_000), sample_rate=16_000)
            await asyncio.sleep(0.3)
            assert uttered == []
            assert gate.last_error is not None
            assert "429" in (gate.last_error or "")
            gate.push(_tone(8_000), sample_rate=16_000)
            await asyncio.sleep(0.3)
            assert uttered == ["Still here after the rate limit."]
            assert gate.last_error is None
        finally:
            await gate.stop()

    asyncio.run(_run())


def test_receive_coalesced_merges_fragments() -> None:
    async def _run() -> None:
        q: asyncio.Queue[Inbound] = asyncio.Queue()
        await q.put(Inbound(text="Absolutely, you're in the right place! Sam The"))
        await q.put(Inbound(text="Concrete Man helps homeowners."))
        inbound = await receive_coalesced(q, gate=None, coalesce_s=0.05)
        assert inbound.text is not None
        assert "Sam The" in inbound.text
        assert "Concrete Man" in inbound.text

    asyncio.run(_run())


def test_receive_coalesced_short_wait_for_complete_sentence(monkeypatch) -> None:
    """Complete agent lines should not burn the full coalesce budget."""
    waits: list[float] = []

    class _Gate:
        busy = False

        async def wait_idle(self, *, timeout_s: float = 8.0, flush_on_timeout: bool = True) -> None:
            waits.append(timeout_s)

    async def _run() -> None:
        q: asyncio.Queue[Inbound] = asyncio.Queue()
        await q.put(Inbound(text="Hi, thanks for calling Sam The Concrete Man. How can I help?"))
        inbound = await receive_coalesced(
            q,
            gate=_Gate(),  # type: ignore[arg-type]
            coalesce_s=0.70,
            coalesce_complete_s=0.20,
            tail_quiet_s=0.0,
        )
        assert inbound.text is not None
        assert waits == [0.20]

    asyncio.run(_run())


def test_receive_coalesced_longer_wait_when_incomplete() -> None:
    waits: list[float] = []

    class _Gate:
        busy = False

        async def wait_idle(self, *, timeout_s: float = 8.0, flush_on_timeout: bool = True) -> None:
            waits.append(timeout_s)

    async def _run() -> None:
        q: asyncio.Queue[Inbound] = asyncio.Queue()
        await q.put(Inbound(text="I understand how frustrating"))
        await receive_coalesced(
            q,
            gate=_Gate(),  # type: ignore[arg-type]
            coalesce_s=0.70,
            coalesce_complete_s=0.20,
            tail_quiet_s=0.0,
        )
        assert waits == [0.70]

    asyncio.run(_run())


def test_receive_coalesced_tail_quiet_merges_restart() -> None:
    """If agent restarts during tail quiet, keep coalescing fragments."""
    waits: list[float] = []
    q: asyncio.Queue[Inbound] = asyncio.Queue()

    class _Gate:
        def __init__(self) -> None:
            self._n = 0

        @property
        def busy(self) -> bool:
            self._n += 1
            # First busy probe during tail quiet → restart.
            return self._n == 1

        async def wait_idle(self, *, timeout_s: float = 8.0, flush_on_timeout: bool = True) -> None:
            waits.append(timeout_s)
            # On the second coalesce (after restart), the continuation arrives.
            if len(waits) == 2:
                await q.put(Inbound(text="How can I help today?"))

    async def _run() -> None:
        await q.put(Inbound(text="Thanks for calling."))
        inbound = await receive_coalesced(
            q,
            gate=_Gate(),  # type: ignore[arg-type]
            coalesce_s=0.5,
            coalesce_complete_s=0.2,
            tail_quiet_s=0.08,
        )
        assert inbound.text is not None
        assert "Thanks for calling" in inbound.text
        assert "How can I help" in inbound.text
        assert len(waits) >= 2

    asyncio.run(_run())
