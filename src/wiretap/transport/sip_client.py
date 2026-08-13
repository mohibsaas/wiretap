"""SIP seam for the PSTN transport.

The transport only ever touches :class:`SipClient`, so the SIP library can be
swapped (NAT/RTP behavior is the riskiest part of a softphone) without reworking
call logic. pyVoIP is the default implementation.

pyVoIP invokes its call callback on its own thread and exposes a blocking audio
API; everything here is therefore plain synchronous code that the transport runs
via ``asyncio.to_thread``.
"""

from __future__ import annotations

import socket
import threading
from abc import ABC, abstractmethod
from contextlib import suppress
from typing import Any

from wiretap.transport.pstn_audio import FRAME_BYTES

DEFAULT_SIP_PORT = 5060
# Twilio answers 423 "Interval too brief" below its Min-Expires of 600s;
# pyVoIP asks for 120 by default.
REGISTRATION_EXPIRES = 600


class SipClient(ABC):
    """A registered softphone that answers one inbound call."""

    @abstractmethod
    def start(self) -> None:
        """Register with the SIP server and begin listening for an INVITE."""

    @abstractmethod
    def wait_for_call(self, timeout: float) -> bool:
        """Block until an inbound call is answered. False on timeout."""

    @abstractmethod
    def is_active(self) -> bool:
        """False once the far end hangs up."""

    @abstractmethod
    def read_audio(self, length: int = FRAME_BYTES) -> bytes:
        """Non-blocking read of 8-bit unsigned linear PCM at 8 kHz."""

    @abstractmethod
    def write_audio(self, payload: bytes) -> None:
        """Queue 8-bit unsigned linear PCM at 8 kHz; the client paces RTP."""

    @abstractmethod
    def stop(self) -> None:
        """Hang up and unregister. Safe to call more than once."""


class PyVoipSipClient(SipClient):
    """pyVoIP-backed softphone registered to a Twilio SIP domain."""

    def __init__(
        self,
        *,
        domain: str,
        username: str,
        password: str,
        port: int = DEFAULT_SIP_PORT,
        sip_port: int = DEFAULT_SIP_PORT,
    ) -> None:
        self._domain = domain
        self._username = username
        self._password = password
        self._port = port
        self._sip_port = sip_port
        self._answered = threading.Event()
        self._call: Any | None = None
        self._phone: Any | None = None

    def start(self) -> None:
        from wiretap.transport.sip_compat import apply_twilio_patches

        voip = _load_pyvoip()  # first, so a missing extra explains itself
        apply_twilio_patches()
        self._phone = voip.VoIPPhone(
            self._domain,
            self._port,
            self._username,
            self._password,
            # pyVoIP defaults to 0.0.0.0 and echoes myIP into its Contact header
            # and SDP, which leaves the carrier no address to ring back.
            myIP=local_ip(),
            callCallback=self._on_inbound_call,
            sipPort=self._sip_port,
        )
        self._phone.sip.default_expires = REGISTRATION_EXPIRES
        self._phone.start()
        self._require_registration(voip)

    def _require_registration(self, voip: Any) -> None:
        """pyVoIP swallows registration failures, so ``start()`` proves nothing."""
        if self._phone.get_status() is voip.PhoneStatus.REGISTERED:
            return
        self.stop()
        raise RuntimeError(
            f"SIP registration to {self._domain} failed as {self._username}. "
            "Verify TWILIO_SIP_PASSWORD matches the 'wiretap' credential in the "
            "Twilio Console (Voice > SIP Domains) and that UDP 5060 is not blocked."
        )

    def _on_inbound_call(self, call: Any) -> None:
        """Runs on a pyVoIP thread — touch nothing but plain locks/events."""
        try:
            call.answer()
        except Exception:  # noqa: BLE001 — a failed answer must not kill the thread
            return
        self._call = call
        self._answered.set()

    def wait_for_call(self, timeout: float) -> bool:
        return self._answered.wait(timeout)

    def is_active(self) -> bool:
        call = self._call
        if call is None:
            return False
        voip = _load_pyvoip()
        return bool(call.state == voip.CallState.ANSWERED)

    def read_audio(self, length: int = FRAME_BYTES) -> bytes:
        call = self._call
        if call is None:
            return b""
        try:
            return call.read_audio(length, False)
        except Exception:  # noqa: BLE001 — a torn-down RTP client reads as silence
            return b""

    def write_audio(self, payload: bytes) -> None:
        call = self._call
        if call is None or not payload:
            return
        with suppress(Exception):
            call.write_audio(payload)

    def stop(self) -> None:
        call, self._call = self._call, None
        if call is not None:
            with suppress(Exception):
                call.hangup()
        phone, self._phone = self._phone, None
        if phone is not None:
            with suppress(Exception):
                phone.stop()


def local_ip() -> str:
    """LAN address on the default route. No packets are sent."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _load_pyvoip() -> Any:
    try:
        from pyVoIP import VoIP
    except ImportError as exc:
        raise RuntimeError(
            "PSTN transport requires pyVoIP. Reinstall with: uv sync --extra pstn"
        ) from exc
    return VoIP


__all__ = ["DEFAULT_SIP_PORT", "PyVoipSipClient", "SipClient", "local_ip"]
