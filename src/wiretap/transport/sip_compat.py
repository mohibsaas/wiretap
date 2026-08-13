"""Twilio-compatible digest auth for pyVoIP.

pyVoIP 1.6.8 cannot register against a Twilio SIP domain. Twilio challenges
REGISTER with ``407 Proxy Authentication Required`` and ``qop="auth"``, whereas
pyVoIP only answers ``401`` -- its 407 branch is an unimplemented stub -- and
only computes the qop-less RFC 2069 digest. An unpatched client therefore never
sends a credentialed REGISTER and gives up with a misleading "Invalid Username
or Password", after which Twilio rejects the call with "Dial a Twilio SIP
Registered User that is not currently registered".

These patches add just the proxy-auth handling; dialogs, RTP and call state stay
with pyVoIP.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

PROXY_AUTHENTICATE = "Proxy-Authenticate"

_applied = False


def apply_twilio_patches() -> None:
    """Teach pyVoIP proxy-digest auth. Idempotent."""
    global _applied
    if _applied:
        return
    from pyVoIP.SIP import SIPClient, SIPMessage, SIPStatus

    _patch_challenge_parsing(SIPMessage, SIPStatus)
    SIPClient.gen_register = _gen_register
    _applied = True


def _patch_challenge_parsing(message_cls: Any, status_cls: Any) -> None:
    """Record ``Proxy-Authenticate`` challenges the way pyVoIP records 401s."""
    original = message_cls.parse_header

    def parse_header(self: Any, header: str, data: str) -> None:
        if header != PROXY_AUTHENTICATE:
            original(self, header, data)
            return
        challenge = {
            key: value.strip('"')
            for key, value in self.auth_match.findall(data.replace("Digest ", ""))
        }
        self.headers[header] = challenge
        self.authentication = challenge
        # pyVoIP only re-sends credentials on a 401, so the proxy challenge is
        # presented as one. The reply picks its header name from the recorded
        # Proxy-Authenticate rather than from the status, so nothing downstream
        # depends on this rewrite. Status is assigned before headers parse.
        self.status = status_cls(401)

    message_cls.parse_header = parse_header


def _gen_register(self: Any, request: Any, deregister: bool = False) -> str:
    """REGISTER carrying a challenge response Twilio accepts."""
    import pyVoIP

    uri = f"sip:{self.server}"
    header = (
        "Proxy-Authorization" if PROXY_AUTHENTICATE in request.headers else "Authorization"
    )
    credentials = build_digest_header(
        username=self.username,
        password=self.password,
        method="REGISTER",
        uri=uri,
        challenge=request.authentication,
    )
    return (
        f"REGISTER {uri} SIP/2.0\r\n"
        f"Via: SIP/2.0/UDP {self.myIP}:{self.myPort};"
        f"branch={self.gen_branch()};rport\r\n"
        f'From: "{self.username}" <sip:{self.username}@{self.server}>;'
        f'tag={self.tagLibrary["register"]}\r\n'
        f'To: "{self.username}" <sip:{self.username}@{self.server}>\r\n'
        f"Call-ID: {request.headers.get('Call-ID', self.gen_call_id())}\r\n"
        f"CSeq: {self.registerCounter.next()} REGISTER\r\n"
        f"Contact: <sip:{self.username}@{self.myIP}:{self.myPort};transport=UDP>;"
        f'+sip.instance="<urn:uuid:{self.urnUUID}>"\r\n'
        f"Allow: {', '.join(pyVoIP.SIPCompatibleMethods)}\r\n"
        "Max-Forwards: 70\r\n"
        "Allow-Events: org.3gpp.nwinitdereg\r\n"
        f"User-Agent: pyVoIP {pyVoIP.__version__}\r\n"
        f"Expires: {0 if deregister else self.default_expires}\r\n"
        f"{header}: {credentials}\r\n"
        "Content-Length: 0\r\n\r\n"
    )


def build_digest_header(
    *,
    username: str,
    password: str,
    method: str,
    uri: str,
    challenge: dict[str, str],
) -> str:
    """RFC 2617 digest credentials, with ``qop=auth`` when the server asks."""
    realm = challenge["realm"]
    nonce = challenge["nonce"]
    ha1 = _md5(f"{username}:{realm}:{password}")
    ha2 = _md5(f"{method}:{uri}")

    params = [
        f'username="{username}"',
        f'realm="{realm}"',
        f'nonce="{nonce}"',
        f'uri="{uri}"',
    ]
    if _supports_auth_qop(challenge.get("qop")):
        cnonce = secrets.token_hex(8)
        count = "00000001"
        response = _md5(f"{ha1}:{nonce}:{count}:{cnonce}:auth:{ha2}")
        params += ["qop=auth", f"nc={count}", f'cnonce="{cnonce}"']
    else:
        response = _md5(f"{ha1}:{nonce}:{ha2}")
    params.append(f'response="{response}"')
    if challenge.get("opaque"):
        params.append(f'opaque="{challenge["opaque"]}"')
    params.append("algorithm=MD5")
    return "Digest " + ",".join(params)


def _supports_auth_qop(value: str | None) -> bool:
    return "auth" in {option.strip() for option in (value or "").split(",")}


def _md5(value: str) -> str:
    """MD5 is what SIP digest mandates (RFC 3261 §22.4); not a general-purpose hash."""
    return hashlib.md5(value.encode("utf8")).hexdigest()


__all__ = ["PROXY_AUTHENTICATE", "apply_twilio_patches", "build_digest_header"]
