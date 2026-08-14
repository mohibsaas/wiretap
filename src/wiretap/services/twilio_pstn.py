"""Twilio REST helpers for the PSTN transport.

Everything here is provisioned through the REST API so wiretap needs no public
endpoint: the local softphone *registers* to a Twilio SIP domain (outbound, so
NAT-friendly) and the bridge leg carries inline TwiML. No webhooks, no tunnels.

The Twilio SDK is synchronous; callers run these in ``asyncio.to_thread``.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import string
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from wiretap.paths import wiretap_root
from wiretap.providers.env import require_env

ACCOUNT_SID_ENV = "TWILIO_ACCOUNT_SID"
AUTH_TOKEN_ENV = "TWILIO_AUTH_TOKEN"
SIP_PASSWORD_ENV = "TWILIO_SIP_PASSWORD"
FROM_NUMBER_ENV = "TWILIO_FROM_NUMBER"

SIP_USERNAME = "wiretap"
CREDENTIAL_LIST_NAME = "wiretap"
SETTINGS_FILENAME = "twilio.json"
# Distribution packages installed by the optional ``pstn`` extra.
PSTN_PACKAGES = ("twilio", "pyVoIP")
# Accounts can hold thousands of numbers; never page through all of them.
NUMBER_PAGE_SIZE = 20

# Twilio rejects SIP passwords below 12 chars or missing a character class.
_PASSWORD_LENGTH = 24
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


@dataclass(frozen=True)
class SipEndpoint:
    """A registrable SIP identity on the user's own Twilio account."""

    domain: str
    username: str
    password: str

    @property
    def uri(self) -> str:
        return f"sip:{self.username}@{self.domain}"


def normalize_e164(value: str | None, *, field: str = "phone number") -> str:
    """Validate a dialable number. Also what keeps generated TwiML injection-free."""
    candidate = re.sub(r"[\s\-().]", "", (value or "").strip())
    if not _E164.match(candidate):
        raise ValueError(
            f"Invalid {field}: {value!r}. Use E.164 format, e.g. +14155550123."
        )
    return candidate


def missing_pstn_packages() -> list[str]:
    """Packages from the optional ``pstn`` extra that are not importable."""
    from importlib.util import find_spec

    return [name for name in PSTN_PACKAGES if find_spec(name) is None]


def pstn_status(cwd: Path | None = None) -> dict[str, Any]:
    """Whether a phone run could place a call right now — presence, never values.

    Shared by `wiretap status` and the dashboard so both judge readiness the
    same way. ``missing`` holds the remaining setup steps, in the order a user
    would do them.
    """
    from wiretap.services.secrets import key_status

    keys = key_status(cwd)
    absent_packages = missing_pstn_packages()
    credentials = bool(keys.get(ACCOUNT_SID_ENV) and keys.get(AUTH_TOKEN_ENV))
    number = resolve_from_number(cwd) or ""

    missing: list[str] = []
    if absent_packages:
        missing.append("uv sync --extra pstn")
    if not credentials:
        missing.append("Twilio keys")
    if not number:
        missing.append("caller number")

    return {
        "ready": not missing,
        "extra_installed": not absent_packages,
        "missing_packages": absent_packages,
        "has_credentials": credentials,
        "from_number": number or None,
        "missing": missing,
        "keys": {
            env: bool(keys.get(env))
            for env in (ACCOUNT_SID_ENV, AUTH_TOKEN_ENV, SIP_PASSWORD_ENV, FROM_NUMBER_ENV)
        },
    }


def twilio_client() -> Any:
    """Authenticated Twilio client built from the wiretap secret store."""
    try:
        from twilio.rest import Client
    except ImportError as exc:
        raise RuntimeError(
            "PSTN transport requires the twilio SDK. "
            "Reinstall with: uv sync --extra pstn"
        ) from exc
    return Client(require_env(ACCOUNT_SID_ENV), require_env(AUTH_TOKEN_ENV))


@contextmanager
def twilio_errors(action: str) -> Iterator[None]:
    """Turn Twilio SDK failures into one-line, actionable messages.

    The SDK raises a bare exception carrying the HTTP response, which surfaces
    as a wall of traceback; a rejected API key deserves a sentence instead.
    """
    from twilio.base.exceptions import TwilioException

    try:
        yield
    except TwilioException as exc:
        status = _http_status(exc)
        if status in {401, 403}:
            raise RuntimeError(
                f"Twilio rejected your credentials while {action} (HTTP {status}). "
                f"Check {ACCOUNT_SID_ENV} and {AUTH_TOKEN_ENV} against the Twilio "
                "Console dashboard — the token must belong to that exact account."
            ) from exc
        detail = f" (HTTP {status})" if status else ""
        raise RuntimeError(f"Twilio failed while {action}{detail}: {exc}") from exc


def _http_status(exc: Exception) -> int | None:
    """Status code from either TwilioRestException or a raw page failure."""
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status
    for arg in getattr(exc, "args", ()):
        code = getattr(arg, "status_code", None)
        if isinstance(code, int):
            return code
    return None


def list_phone_numbers(
    client: Any | None = None,
    *,
    limit: int = NUMBER_PAGE_SIZE,
    contains: str | None = None,
) -> list[dict[str, str]]:
    """Numbers on the account, usable as the caller id for the test agent.

    Paged deliberately: a large account holds thousands of numbers, and reading
    every page costs a minute for a list nobody can scroll. ``contains`` is a
    partial-number search handled by Twilio.
    """
    client = client or twilio_client()
    numbers = []
    query: dict[str, Any] = {"limit": limit, "page_size": limit}
    if contains:
        query["phone_number"] = contains
    with twilio_errors("listing your phone numbers"):
        records = client.incoming_phone_numbers.list(**query)
    for record in records:
        number = (getattr(record, "phone_number", "") or "").strip()
        if number:
            numbers.append(
                {
                    "phone_number": number,
                    "friendly_name": (getattr(record, "friendly_name", "") or "").strip(),
                }
            )
    return sorted(numbers, key=lambda n: n["phone_number"])


def ensure_sip_endpoint(client: Any | None = None) -> SipEndpoint:
    """Idempotently provision the SIP domain, credential and registration mapping."""
    client = client or twilio_client()
    domain_name = sip_domain_name(client.account_sid)

    with twilio_errors("provisioning your SIP endpoint"):
        return _provision(client, domain_name)


def _provision(client: Any, domain_name: str) -> SipEndpoint:
    domain = _find(client.sip.domains.list(), "domain_name", domain_name)
    if domain is None:
        domain = client.sip.domains.create(
            domain_name=domain_name,
            friendly_name="wiretap",
            sip_registration=True,
        )
    elif not getattr(domain, "sip_registration", False):
        domain = client.sip.domains(domain.sid).update(sip_registration=True)

    credential_list = _find(
        client.sip.credential_lists.list(), "friendly_name", CREDENTIAL_LIST_NAME
    )
    if credential_list is None:
        credential_list = client.sip.credential_lists.create(
            friendly_name=CREDENTIAL_LIST_NAME
        )

    password = _ensure_credential(client, credential_list.sid)
    _ensure_registration_mapping(client, domain.sid, credential_list.sid)
    return SipEndpoint(domain=domain_name, username=SIP_USERNAME, password=password)


def sip_domain_name(account_sid: str) -> str:
    """Per-account domain — Twilio SIP domains are globally unique."""
    return f"wiretap-{account_sid[-10:].lower()}.sip.twilio.com"


def _ensure_credential(client: Any, credential_list_sid: str) -> str:
    """Return the SIP password, rotating the credential when we no longer hold it.

    Twilio never discloses a stored password, so a local copy is the only usable
    one; if it is gone the credential is reset rather than left unusable.
    """
    from wiretap.services.secrets import upsert_secrets

    credentials = client.sip.credential_lists(credential_list_sid).credentials
    existing = _find(credentials.list(), "username", SIP_USERNAME)
    password = (os.environ.get(SIP_PASSWORD_ENV) or "").strip()

    if password and existing is not None:
        return password
    if not password:
        password = generate_sip_password()
    if existing is None:
        credentials.create(username=SIP_USERNAME, password=password)
    else:
        credentials(existing.sid).update(password=password)
    upsert_secrets({SIP_PASSWORD_ENV: password})
    return password


def _ensure_registration_mapping(
    client: Any, domain_sid: str, credential_list_sid: str
) -> None:
    mappings = client.sip.domains(domain_sid).auth.registrations.credential_list_mappings
    for mapping in mappings.list():
        if getattr(mapping, "sid", None) == credential_list_sid:
            return
        if getattr(mapping, "friendly_name", None) == CREDENTIAL_LIST_NAME:
            return
    mappings.create(credential_list_sid=credential_list_sid)


def generate_sip_password(length: int = _PASSWORD_LENGTH) -> str:
    """Twilio policy: 12+ chars with upper, lower and digit."""
    alphabet = string.ascii_letters + string.digits
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in candidate)
            and any(c.isupper() for c in candidate)
            and any(c.isdigit() for c in candidate)
        ):
            return candidate


def bridge_twiml(to_number: str, from_number: str) -> str:
    """Inline TwiML that bridges the answered SIP leg to the agent's number."""
    to_number = normalize_e164(to_number, field="agent phone number")
    from_number = normalize_e164(from_number, field="caller number")
    return (
        "<Response>"
        f"<Dial callerId={quoteattr(from_number)} answerOnBridge=\"true\">"
        f"<Number>{escape(to_number)}</Number>"
        "</Dial></Response>"
    )


def place_bridge_call(
    *,
    to_number: str,
    from_number: str,
    sip_uri: str,
    client: Any | None = None,
) -> str:
    """Call our registered softphone, then bridge it to the agent. Returns the SID."""
    client = client or twilio_client()
    with twilio_errors(f"dialing {to_number}"):
        call = client.calls.create(
            to=sip_uri,
            from_=normalize_e164(from_number, field="caller number"),
            twiml=bridge_twiml(to_number, from_number),
        )
    return str(call.sid)


def hangup_call(call_sid: str, client: Any | None = None) -> None:
    """Best-effort end of the outbound leg — never raises."""
    if not call_sid:
        return
    try:
        client = client or twilio_client()
        client.calls(call_sid).update(status="completed")
    except Exception:  # noqa: BLE001 — teardown must not fail a completed run
        return


def settings_path(cwd: Path | None = None) -> Path:
    return wiretap_root(cwd) / SETTINGS_FILENAME


def saved_from_number(cwd: Path | None = None) -> str | None:
    """Caller number the user picked on a previous run."""
    path = settings_path(cwd)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    number = str((data or {}).get("from_number") or "").strip()
    return number or None


def save_from_number(number: str, cwd: Path | None = None) -> str:
    """Persist the picker choice so later runs are non-interactive."""
    number = normalize_e164(number, field="caller number")
    path = settings_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError):
            data = {}
    data["from_number"] = number
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return number


def resolve_from_number(cwd: Path | None = None) -> str | None:
    """Env override first, then the saved picker choice."""
    from_env = (os.environ.get(FROM_NUMBER_ENV) or "").strip()
    return from_env or saved_from_number(cwd)


def _find(records: list[Any], attribute: str, value: str) -> Any | None:
    return next((r for r in records if getattr(r, attribute, None) == value), None)


__all__ = [
    "ACCOUNT_SID_ENV",
    "AUTH_TOKEN_ENV",
    "CREDENTIAL_LIST_NAME",
    "FROM_NUMBER_ENV",
    "PSTN_PACKAGES",
    "SIP_PASSWORD_ENV",
    "SIP_USERNAME",
    "SipEndpoint",
    "bridge_twiml",
    "ensure_sip_endpoint",
    "generate_sip_password",
    "hangup_call",
    "list_phone_numbers",
    "missing_pstn_packages",
    "normalize_e164",
    "place_bridge_call",
    "pstn_status",
    "resolve_from_number",
    "save_from_number",
    "saved_from_number",
    "settings_path",
    "sip_domain_name",
    "twilio_client",
    "twilio_errors",
]
