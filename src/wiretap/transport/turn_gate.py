"""Shared agent-audio turn gate — provider-agnostic silence endpointing + batch STT.

Used by Retell, LiveKit, Vapi WS, Synthflow, and any future live audio transport.
Turn boundaries come from energy VAD + configured STT (pyai/openai/deepgram/…).
Provider talk events / live transcripts are optional and never required.

Latency budget (critical path after agent stops talking):
  silence endpoint → batch STT → optional coalesce → caller LLM → TTS → publish.
Keep silence/coalesce/speak-idle tight; do not reintroduce holdback re-STT.
"""

from __future__ import annotations

import asyncio
import inspect
import math
import time
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field
from typing import TypeVar

from wiretap.providers.factory import build_stt
from wiretap.providers.speech import AudioBuffer, SpeechToTextProvider
from wiretap.transport.audio_util import downsample_pcm16
from wiretap.transport.base import Inbound
from wiretap.transport.transcript_util import (
    accept_final_utterance,
    coalesce_utterances,
    looks_incomplete_utterance,
)

OnUtterance = Callable[..., None | Awaitable[None]]
T = TypeVar("T")
ElapsedMs = Callable[[], float]

# Balance: low enough for acceptable reply latency, high enough to avoid
# mid-clause barge-in that shreds provider transcripts (stakeholder eval).
DEFAULT_SILENCE_S = 0.55
DEFAULT_COALESCE_S = 0.85
DEFAULT_COALESCE_COMPLETE_S = 0.45
# Only waits when the gate is still busy — idle returns immediately.
DEFAULT_SPEAK_IDLE_S = 1.25
# After the gate looks idle, require this much continued quiet before we reply.
DEFAULT_TAIL_QUIET_S = 0.35
_STT_TARGET_RATE = 16_000
_MAX_TAIL_ROUNDS = 3


def pcm16_rms(pcm: bytes) -> float:
    """Root-mean-square energy of little-endian PCM16 mono (subsampled)."""
    n = len(pcm) // 2
    if n <= 0:
        return 0.0
    mv = memoryview(pcm).cast("h")
    step = 1 if n <= 320 else max(1, n // 320)
    acc = 0.0
    count = 0
    for i in range(0, n, step):
        s = float(mv[i])
        acc += s * s
        count += 1
    return (acc / count) ** 0.5 if count else 0.0


@dataclass
class AgentTurnGate:
    """Buffer remote agent PCM; on sustained silence, STT one utterance.

    Works with any batch STT from ``build_stt``. Fragment merging after a first
    emission is handled by ``receive_coalesced`` — do not stack holdback STT
    on the critical path (that destroyed reply latency).
    """

    stt_name: str = "pyai"
    silence_s: float = DEFAULT_SILENCE_S
    min_speech_bytes: int = 10_000  # ~0.3s @ 16 kHz
    energy_threshold: float = 350.0
    poll_s: float = 0.05
    max_buffer_bytes: int = 480_000
    on_utterance: OnUtterance | None = None
    # Optional CallRecorder.elapsed_ms — aligns STT turns to the mixed WAV.
    elapsed_ms_fn: ElapsedMs | None = None

    _buf: bytearray = field(default_factory=bytearray, init=False, repr=False)
    _sample_rate: int = field(default=16_000, init=False, repr=False)
    _last_voice_at: float = field(default=0.0, init=False, repr=False)
    # CallRecorder ms when the current buffered utterance first got voice.
    _span_start_ms: float | None = field(default=None, init=False, repr=False)
    _seen: set[str] = field(default_factory=set, init=False, repr=False)
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _flushing: bool = field(default=False, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _muted: bool = field(default=False, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _stt: SpeechToTextProvider | None = field(default=None, init=False, repr=False)
    _stt_for: str = field(default="", init=False, repr=False)
    last_error: str | None = field(default=None, init=False)
    last_stt_ms: float | None = field(default=None, init=False)

    def configure(self, *, stt: str | None = None) -> None:
        if stt and stt != self.stt_name:
            self.stt_name = stt
            self._stt = None
            self._stt_for = ""

    def set_elapsed_ms_fn(self, fn: ElapsedMs | None) -> None:
        self.elapsed_ms_fn = fn

    def _get_stt(self) -> SpeechToTextProvider:
        if self._stt is None or self._stt_for != self.stt_name:
            self._stt = build_stt(self.stt_name)
            self._stt_for = self.stt_name
        return self._stt

    @property
    def muted(self) -> bool:
        return self._muted

    def mute(self) -> None:
        """Ignore remote audio while caller TTS is publishing."""
        self._muted = True
        self._buf.clear()
        self._last_voice_at = 0.0
        self._span_start_ms = None

    def unmute(self, *, clear: bool = True) -> None:
        """Resume turn detection after caller TTS."""
        self._muted = False
        if clear:
            self._buf.clear()
            self._last_voice_at = 0.0
            self._span_start_ms = None

    @property
    def busy(self) -> bool:
        if self._muted:
            return False
        return bool(self._buf) or self._flushing or (
            self._last_voice_at > 0
            and (time.monotonic() - self._last_voice_at) < self.silence_s
        )

    def push(self, pcm: bytes, *, sample_rate: int) -> None:
        if self._closed or self._muted or not pcm:
            return
        if sample_rate > 0:
            self._sample_rate = int(sample_rate)
        if pcm16_rms(pcm) < self.energy_threshold:
            return
        # Mark WAV timeline start on first voiced frame of this utterance.
        if not self._buf and self.elapsed_ms_fn is not None:
            try:
                self._span_start_ms = float(self.elapsed_ms_fn())
            except Exception:
                self._span_start_ms = None
        self._buf.extend(pcm)
        self._last_voice_at = time.monotonic()
        if len(self._buf) >= self.max_buffer_bytes:
            self._last_voice_at = time.monotonic() - self.silence_s - 0.01

    async def start(self) -> None:
        if self._task is not None:
            return
        self._closed = False
        self._task = asyncio.create_task(self._poll_loop(), name="agent-turn-gate")

    async def stop(self) -> None:
        self._closed = True
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self.flush(force=True)
        stt = self._stt
        self._stt = None
        self._stt_for = ""
        close = getattr(stt, "aclose", None) if stt is not None else None
        if callable(close):
            try:
                await close()
            except Exception:
                pass

    async def wait_idle(
        self, *, timeout_s: float = 8.0, flush_on_timeout: bool = True
    ) -> None:
        if timeout_s <= 0:
            if flush_on_timeout and self._buf and not self._flushing:
                await self.flush(force=True)
            return
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not self.busy:
                return
            await asyncio.sleep(0.03)
        if flush_on_timeout and self._buf:
            await self.flush(force=True)

    async def flush(self, *, force: bool = False) -> str | None:
        async with self._lock:
            if self._flushing:
                return None
            if not self._buf:
                return None
            if not force and len(self._buf) < self.min_speech_bytes:
                self._buf.clear()
                self._span_start_ms = None
                return None
            pcm = bytes(self._buf)
            rate = self._sample_rate or 16_000
            span_start = self._span_start_ms
            self._buf.clear()
            # Endpoint committed — don't look "busy" from stale voice timestamp
            # while STT runs (that bloated coalesce waits).
            self._last_voice_at = 0.0
            self._flushing = True
            # Capture WAV offset before STT await (more audio may append meanwhile).
            start_ms, end_ms = self._span_for_pcm(pcm, rate, span_start=span_start)
            self._span_start_ms = None

        try:
            if rate != _STT_TARGET_RATE:
                pcm = downsample_pcm16(pcm, rate, _STT_TARGET_RATE)
                rate = _STT_TARGET_RATE
            stt = self._get_stt()
            t0 = time.perf_counter()
            text = await stt.transcribe(AudioBuffer(pcm=pcm, sample_rate=rate))
            self.last_stt_ms = (time.perf_counter() - t0) * 1000.0
            text = (text or "").strip()
            if not text:
                return None
            self.last_error = None
            return await self._emit(text, start_ms=start_ms, end_ms=end_ms)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Never kill the poll loop on provider blips (429, timeouts, …).
            self.last_error = f"{type(exc).__name__}: {exc}"[:240]
            return None
        finally:
            self._flushing = False

    def _span_for_pcm(
        self,
        pcm: bytes,
        rate: int,
        *,
        span_start: float | None = None,
    ) -> tuple[float | None, float | None]:
        """Map a flushed speech buffer onto the CallRecorder timeline.

        Prefer the recorder mark from the first voiced frame of this utterance
        (includes mid-utterance pauses in the WAV). Fall back to buffer length.
        """
        if self.elapsed_ms_fn is None or rate <= 0:
            return None, None
        try:
            now = float(self.elapsed_ms_fn())
        except Exception:
            return None, None
        speech_ms = (len(pcm) / 2.0 / float(rate)) * 1000.0
        # Quiet frames after last voice still land in the WAV during silence_s.
        end_ms = max(0.0, now - float(self.silence_s) * 1000.0)
        if span_start is not None and math.isfinite(span_start):
            start_ms = max(0.0, min(float(span_start), end_ms))
        else:
            start_ms = max(0.0, end_ms - speech_ms)
        # Guard: never shorter than the energetic buffer we actually STT'd.
        if end_ms - start_ms < speech_ms * 0.5:
            start_ms = max(0.0, end_ms - speech_ms)
        if end_ms < start_ms:
            end_ms = start_ms
        return start_ms, end_ms

    async def _emit(
        self,
        text: str,
        *,
        start_ms: float | None = None,
        end_ms: float | None = None,
    ) -> str | None:
        accepted = accept_final_utterance(text, self._seen)
        if accepted and self.on_utterance is not None:
            result = self._invoke_utterance(
                accepted, start_ms=start_ms, end_ms=end_ms
            )
            if inspect.isawaitable(result):
                await result
        return accepted

    def _invoke_utterance(
        self,
        text: str,
        *,
        start_ms: float | None,
        end_ms: float | None,
    ) -> None | Awaitable[None]:
        assert self.on_utterance is not None
        try:
            return self.on_utterance(text, start_ms=start_ms, end_ms=end_ms)
        except TypeError:
            # Legacy callbacks: on_utterance(text) only
            return self.on_utterance(text)

    async def _poll_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(self.poll_s)
                if self._muted or self._flushing or not self._buf:
                    continue
                idle = time.monotonic() - self._last_voice_at
                if idle < self.silence_s:
                    continue
                if len(self._buf) < self.min_speech_bytes:
                    self._buf.clear()
                    continue
                try:
                    await self.flush(force=True)
                except Exception as exc:
                    self.last_error = f"{type(exc).__name__}: {exc}"[:240]
        except asyncio.CancelledError:
            raise


async def receive_coalesced(
    pending: asyncio.Queue[Inbound],
    gate: AgentTurnGate | None,
    *,
    connected: bool = True,
    timeout_s: float = 45.0,
    coalesce_s: float = DEFAULT_COALESCE_S,
    coalesce_complete_s: float = DEFAULT_COALESCE_COMPLETE_S,
    tail_quiet_s: float = DEFAULT_TAIL_QUIET_S,
) -> Inbound:
    """Wait for one agent turn; merge early fragments until the gate stays quiet.

    Provider-agnostic: works for any transport that feeds ``pending`` via the
    shared turn gate (Retell, LiveKit, Vapi WS, Synthflow, …).
    """
    if not connected:
        return Inbound(hung_up=True)
    try:
        first = await asyncio.wait_for(pending.get(), timeout=timeout_s)
    except TimeoutError:
        return Inbound(hung_up=True)
    if first.hung_up:
        return first
    parts: list[str] = []
    start_ms = first.start_ms
    end_ms = first.end_ms
    if first.text:
        parts.append(first.text)

    def _absorb(more: Inbound) -> None:
        nonlocal start_ms, end_ms
        if more.text:
            parts.append(more.text)
        if more.start_ms is not None:
            start_ms = (
                more.start_ms
                if start_ms is None
                else min(start_ms, more.start_ms)
            )
        if more.end_ms is not None:
            end_ms = (
                more.end_ms if end_ms is None else max(end_ms, more.end_ms)
            )

    async def _drain() -> bool:
        """Pull queued fragments. Returns True if hangup was seen (re-queued)."""
        hung = False
        while True:
            try:
                more = pending.get_nowait()
            except asyncio.QueueEmpty:
                break
            if more.hung_up:
                await pending.put(more)
                hung = True
                break
            _absorb(more)
        return hung

    async def _coalesce_wait() -> None:
        if gate is None:
            return
        text_so_far = coalesce_utterances(parts)
        wait = coalesce_s
        if text_so_far and not looks_incomplete_utterance(text_so_far):
            wait = min(coalesce_s, coalesce_complete_s)
        await gate.wait_idle(timeout_s=wait, flush_on_timeout=True)

    if gate is not None:
        await _coalesce_wait()
        if await _drain():
            return Inbound(
                text=coalesce_utterances(parts) or None,
                hung_up=False,
                start_ms=start_ms,
                end_ms=end_ms,
            )

        # Tail-quiet confirmation: if the agent restarts after a brief pause,
        # keep merging instead of barging in (was shredding Retell/Vapi finals).
        for _ in range(_MAX_TAIL_ROUNDS):
            if tail_quiet_s <= 0:
                break
            restarted = False
            deadline = time.monotonic() + tail_quiet_s
            while time.monotonic() < deadline:
                if gate.busy:
                    restarted = True
                    break
                await asyncio.sleep(0.03)
            if not restarted:
                break
            await _coalesce_wait()
            if await _drain():
                break
    else:
        await _drain()

    text = coalesce_utterances(parts)
    return Inbound(
        text=text or None,
        start_ms=start_ms,
        end_ms=end_ms,
    )


async def speak_with_gate_mute(
    gate: AgentTurnGate | None,
    speak: Callable[[], Coroutine[object, object, T]],
    *,
    idle_s: float = DEFAULT_SPEAK_IDLE_S,
) -> T:
    """Mute the turn gate while publishing caller audio (any transport).

    Waits for the remote agent to go idle before muting — cheap when already
    idle, prevents talking over residual agent speech when not.
    """
    if gate is not None:
        await gate.wait_idle(timeout_s=idle_s, flush_on_timeout=False)
        gate.mute()
    try:
        return await speak()
    finally:
        if gate is not None:
            gate.unmute(clear=True)
