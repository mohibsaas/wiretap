"""Softphone startup guards.

pyVoIP swallows registration failures inside ``register()`` and returns from
``start()`` as if nothing happened, so the transport used to dial Twilio with an
unregistered softphone and only learn about it from a carrier error.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from wiretap.transport.sip_client import REGISTRATION_EXPIRES, PyVoipSipClient, local_ip

pytest.importorskip("pyVoIP", reason="PSTN extra not installed")


class FakePhone:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        self.sip = SimpleNamespace(default_expires=120)
        self.started = False
        self.stopped = False
        self.status: Any = None

    def start(self) -> None:
        self.started = True

    def get_status(self) -> Any:
        return self.status

    def stop(self) -> None:
        self.stopped = True


def fake_pyvoip(status_name: str) -> tuple[Any, list[FakePhone]]:
    from pyVoIP.VoIP.status import PhoneStatus

    built: list[FakePhone] = []

    def build(*args: Any, **kwargs: Any) -> FakePhone:
        phone = FakePhone(*args, **kwargs)
        phone.status = getattr(PhoneStatus, status_name)
        built.append(phone)
        return phone

    return SimpleNamespace(VoIPPhone=build, PhoneStatus=PhoneStatus), built


def client() -> PyVoipSipClient:
    return PyVoipSipClient(
        domain="wiretap-abc.sip.twilio.com", username="wiretap", password="Secret123456"
    )


def test_start_binds_a_routable_address_and_twilios_minimum_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, built = fake_pyvoip("REGISTERED")
    monkeypatch.setattr("wiretap.transport.sip_client._load_pyvoip", lambda: module)

    client().start()

    (phone,) = built
    assert phone.started
    # 0.0.0.0 is pyVoIP's default and lands in Contact/SDP, leaving the carrier
    # nowhere to ring back.
    assert phone.kwargs["myIP"] not in {"0.0.0.0", ""}
    assert phone.sip.default_expires == REGISTRATION_EXPIRES


def test_start_fails_loudly_when_registration_did_not_take(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, built = fake_pyvoip("REGISTERING")
    monkeypatch.setattr("wiretap.transport.sip_client._load_pyvoip", lambda: module)

    with pytest.raises(RuntimeError, match=r"SIP registration to wiretap-abc"):
        client().start()

    assert built[0].stopped


def test_local_ip_is_a_concrete_address() -> None:
    assert local_ip() not in {"0.0.0.0", ""}
