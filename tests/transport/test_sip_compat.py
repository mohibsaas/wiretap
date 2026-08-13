"""Twilio proxy-digest auth for pyVoIP.

Twilio challenges REGISTER with 407 + ``qop="auth"``; stock pyVoIP answers only
401 with a qop-less digest and so never registers. These tests pin the three
behaviours that make registration work.
"""

from __future__ import annotations

import hashlib
import re

import pytest

from wiretap.transport.sip_compat import apply_twilio_patches, build_digest_header

pytest.importorskip("pyVoIP", reason="PSTN extra not installed")

REALM = "sip.twilio.com"
NONCE = "XUGzTXyAlfGwi-VVMcrYdYcTqgLjr8ab"
OPAQUE = "eb39d5f922374d19b81dbd9ed22f10ff"
URI = "sip:wiretap-abc.sip.twilio.com"


def md5(value: str) -> str:
    return hashlib.md5(value.encode("utf8")).hexdigest()


def param(header: str, name: str) -> str:
    match = re.search(rf'{name}="?([^",]+)"?', header)
    assert match, f"{name} missing from {header}"
    return match.group(1)


def challenge(**overrides: str) -> dict[str, str]:
    return {"realm": REALM, "nonce": NONCE, "qop": "auth", "opaque": OPAQUE} | overrides


def proxy_challenge_response() -> bytes:
    return (
        b"SIP/2.0 407 Proxy Authentication required\r\n"
        b"CSeq: 1 REGISTER\r\n"
        b"Call-ID: abc@1.2.3.4\r\n"
        b'From: "wiretap" <sip:wiretap@d.sip.twilio.com>;tag=aaa\r\n'
        b'To: "wiretap" <sip:wiretap@d.sip.twilio.com>;tag=bbb\r\n'
        b"Via: SIP/2.0/UDP 1.2.3.4:5060;branch=z9hG4bK1;rport=5913\r\n"
        b"Server: Twilio\r\n"
        b'Proxy-Authenticate: Digest realm="' + REALM.encode() + b'",'
        b'qop="auth",nonce="' + NONCE.encode() + b'",opaque="' + OPAQUE.encode() + b'"\r\n'
        b"Content-Length: 0\r\n\r\n"
    )


def test_qop_digest_matches_rfc2617() -> None:
    header = build_digest_header(
        username="wiretap",
        password="Secret123456",
        method="REGISTER",
        uri=URI,
        challenge=challenge(),
    )

    cnonce = param(header, "cnonce")
    ha1 = md5(f"wiretap:{REALM}:Secret123456")
    ha2 = md5(f"REGISTER:{URI}")
    assert param(header, "qop") == "auth"
    assert param(header, "nc") == "00000001"
    assert param(header, "opaque") == OPAQUE
    assert param(header, "response") == md5(
        f"{ha1}:{NONCE}:00000001:{cnonce}:auth:{ha2}"
    )


def test_digest_falls_back_to_rfc2069_without_qop() -> None:
    header = build_digest_header(
        username="wiretap",
        password="Secret123456",
        method="REGISTER",
        uri=URI,
        challenge={"realm": REALM, "nonce": NONCE},
    )

    ha1 = md5(f"wiretap:{REALM}:Secret123456")
    ha2 = md5(f"REGISTER:{URI}")
    assert "qop" not in header
    assert "cnonce" not in header
    assert param(header, "response") == md5(f"{ha1}:{NONCE}:{ha2}")


def test_cnonce_is_not_reused_across_challenges() -> None:
    headers = {
        build_digest_header(
            username="wiretap",
            password="Secret123456",
            method="REGISTER",
            uri=URI,
            challenge=challenge(),
        )
        for _ in range(5)
    }

    assert len(headers) == 5


def test_proxy_challenge_is_parsed_and_routed_to_the_401_retry() -> None:
    from pyVoIP.SIP import SIPMessage, SIPStatus

    apply_twilio_patches()
    message = SIPMessage(proxy_challenge_response())

    assert message.authentication["nonce"] == NONCE
    assert message.authentication["qop"] == "auth"
    # pyVoIP only re-sends credentials on a 401, so the proxy challenge takes
    # that path; without this the register loop dies as "invalid password".
    assert message.status == SIPStatus(401)


def test_register_answers_a_proxy_challenge_with_proxy_authorization() -> None:
    from pyVoIP.SIP import SIPClient, SIPMessage

    apply_twilio_patches()
    client = SIPClient(
        "wiretap-abc.sip.twilio.com", 5060, "wiretap", "Secret123456", phone=None
    )
    request = client.gen_register(SIPMessage(proxy_challenge_response()))

    assert "Proxy-Authorization: Digest " in request
    assert "\r\nAuthorization:" not in request
    assert f"Expires: {client.default_expires}\r\n" in request
    assert request.startswith(f"REGISTER sip:{client.server} SIP/2.0\r\n")


def test_deregister_asks_for_zero_expiry() -> None:
    from pyVoIP.SIP import SIPClient, SIPMessage

    apply_twilio_patches()
    client = SIPClient(
        "wiretap-abc.sip.twilio.com", 5060, "wiretap", "Secret123456", phone=None
    )
    request = client.gen_register(SIPMessage(proxy_challenge_response()), deregister=True)

    assert "Expires: 0\r\n" in request
