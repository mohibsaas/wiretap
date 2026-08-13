"""Twilio provisioning, TwiML generation and caller-number persistence.

A fake stands in for the Twilio SDK client: it mirrors the resource paths the
service uses and records writes, so provisioning idempotence is observable
without any network.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from wiretap.services import twilio_pstn as svc

ACCOUNT_SID = "AC" + "0" * 30 + "abcdef"


class _Record:
    def __init__(self, **fields: Any) -> None:
        self.__dict__.update(fields)


class _Credentials:
    def __init__(self, store: list[_Record], log: list[str]) -> None:
        self._store = store
        self._log = log

    def list(self) -> list[_Record]:
        return list(self._store)

    def create(self, username: str, password: str) -> _Record:
        self._log.append(f"credential.create:{username}")
        record = _Record(sid="CR1", username=username, password=password)
        self._store.append(record)
        return record

    def __call__(self, sid: str) -> _Credentials:
        self._sid = sid
        return self

    def update(self, password: str) -> _Record:
        self._log.append("credential.update")
        self._store[0].password = password
        return self._store[0]


class _Mappings:
    def __init__(self, store: list[_Record], log: list[str]) -> None:
        self._store = store
        self._log = log

    def list(self) -> list[_Record]:
        return list(self._store)

    def create(self, credential_list_sid: str) -> _Record:
        self._log.append("mapping.create")
        record = _Record(sid=credential_list_sid, friendly_name=svc.CREDENTIAL_LIST_NAME)
        self._store.append(record)
        return record


class FakeTwilio:
    """Minimal stand-in for ``twilio.rest.Client``."""

    def __init__(
        self,
        *,
        domains: list[_Record] | None = None,
        credential_lists: list[_Record] | None = None,
        credentials: list[_Record] | None = None,
        mappings: list[_Record] | None = None,
        numbers: list[_Record] | None = None,
    ) -> None:
        self.account_sid = ACCOUNT_SID
        self.log: list[str] = []
        self._domains = domains if domains is not None else []
        self._credential_lists = (
            credential_lists if credential_lists is not None else []
        )
        self._credentials = credentials if credentials is not None else []
        self._mappings = mappings if mappings is not None else []
        self._numbers = numbers if numbers is not None else []
        self.created_calls: list[dict[str, Any]] = []
        self.completed_calls: list[str] = []
        self.sip = _Sip(self)
        self.incoming_phone_numbers = _Numbers(self._numbers)
        # Twilio's ``calls`` is both a list resource and a context factory.
        self.calls = _CallsList(self)


class _Numbers:
    def __init__(self, store: list[_Record]) -> None:
        self._store = store
        self.queries: list[dict[str, Any]] = []

    def list(self, **query: Any) -> list[_Record]:
        self.queries.append(query)
        records = self._store
        if query.get("phone_number"):
            records = [r for r in records if query["phone_number"] in r.phone_number]
        return list(records)[: query.get("limit", len(records))]


class _CallsList:
    def __init__(self, client: FakeTwilio) -> None:
        self._client = client

    def create(self, to: str, from_: str, twiml: str) -> _Record:
        self._client.created_calls.append({"to": to, "from_": from_, "twiml": twiml})
        return _Record(sid="CA123")

    def __call__(self, sid: str) -> _CallContext:
        return _CallContext(self._client, sid)


class _CallContext:
    def __init__(self, client: FakeTwilio, sid: str) -> None:
        self._client = client
        self._sid = sid

    def update(self, status: str) -> None:
        self._client.completed_calls.append(f"{self._sid}:{status}")


class _Sip:
    def __init__(self, client: FakeTwilio) -> None:
        self._client = client
        self.domains = _DomainList(client)
        self.credential_lists = _CredentialListList(client)


class _DomainList:
    def __init__(self, client: FakeTwilio) -> None:
        self._client = client

    def list(self) -> list[_Record]:
        return list(self._client._domains)

    def create(self, domain_name: str, friendly_name: str, sip_registration: bool) -> _Record:
        self._client.log.append("domain.create")
        record = _Record(
            sid="SD1", domain_name=domain_name, sip_registration=sip_registration
        )
        self._client._domains.append(record)
        return record

    def __call__(self, sid: str) -> _DomainContext:
        return _DomainContext(self._client)


class _DomainContext:
    def __init__(self, client: FakeTwilio) -> None:
        self._client = client
        self.auth = _Record(
            registrations=_Record(
                credential_list_mappings=_Mappings(client._mappings, client.log)
            )
        )

    def update(self, sip_registration: bool) -> _Record:
        self._client.log.append("domain.update")
        self._client._domains[0].sip_registration = sip_registration
        return self._client._domains[0]


class _CredentialListList:
    def __init__(self, client: FakeTwilio) -> None:
        self._client = client

    def list(self) -> list[_Record]:
        return list(self._client._credential_lists)

    def create(self, friendly_name: str) -> _Record:
        self._client.log.append("credential_list.create")
        record = _Record(sid="CL1", friendly_name=friendly_name)
        self._client._credential_lists.append(record)
        return record

    def __call__(self, sid: str) -> _Record:
        return _Record(
            credentials=_Credentials(self._client._credentials, self._client.log)
        )


def _provisioned() -> FakeTwilio:
    """An account where wiretap has already set everything up."""
    return FakeTwilio(
        domains=[
            _Record(
                sid="SD1",
                domain_name=svc.sip_domain_name(ACCOUNT_SID),
                sip_registration=True,
            )
        ],
        credential_lists=[_Record(sid="CL1", friendly_name=svc.CREDENTIAL_LIST_NAME)],
        credentials=[_Record(sid="CR1", username=svc.SIP_USERNAME, password="old")],
        mappings=[_Record(sid="CL1", friendly_name=svc.CREDENTIAL_LIST_NAME)],
    )


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WIRETAP_HOME", str(tmp_path))
    monkeypatch.delenv(svc.SIP_PASSWORD_ENV, raising=False)
    monkeypatch.delenv(svc.FROM_NUMBER_ENV, raising=False)


def test_missing_pstn_extra_says_how_to_install_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "twilio.rest", None)

    with pytest.raises(RuntimeError, match=r"uv sync --extra pstn"):
        svc.twilio_client()


def test_missing_sip_library_says_how_to_install_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from wiretap.transport.sip_client import PyVoipSipClient

    monkeypatch.setitem(sys.modules, "pyVoIP", None)
    client = PyVoipSipClient(domain="d", username="u", password="Password1234")

    with pytest.raises(RuntimeError, match=r"uv sync --extra pstn"):
        client.start()


def _rejecting_client(status: int) -> Any:
    """A client whose every read fails the way the Twilio SDK actually fails."""
    from twilio.base.exceptions import TwilioException

    class Response:
        status_code = status
        text = '{"code":20003,"message":"Authenticate"}'

    class Failing:
        def list(self, **kwargs: Any) -> Any:
            raise TwilioException("Unable to fetch page", Response())

        def create(self, **kwargs: Any) -> Any:
            raise TwilioException("Unable to create record", Response())

    client = FakeTwilio()
    client.incoming_phone_numbers = Failing()
    client.sip.domains = Failing()
    client.calls = Failing()
    return client


def test_a_rejected_api_key_reads_as_one_sentence_not_a_traceback() -> None:
    with pytest.raises(RuntimeError) as caught:
        svc.list_phone_numbers(_rejecting_client(401))

    message = str(caught.value)
    assert "rejected your credentials" in message
    assert "401" in message
    assert svc.ACCOUNT_SID_ENV in message and svc.AUTH_TOKEN_ENV in message


def test_a_forbidden_key_is_reported_the_same_way() -> None:
    with pytest.raises(RuntimeError, match="rejected your credentials"):
        svc.list_phone_numbers(_rejecting_client(403))


def test_provisioning_and_dialing_translate_auth_failures_too() -> None:
    with pytest.raises(RuntimeError, match="provisioning your SIP endpoint"):
        svc.ensure_sip_endpoint(_rejecting_client(401))

    with pytest.raises(RuntimeError, match=r"dialing \+14155550123"):
        svc.place_bridge_call(
            to_number="+14155550123",
            from_number="+14155550199",
            sip_uri="sip:wiretap@example.sip.twilio.com",
            client=_rejecting_client(401),
        )


def test_non_auth_failures_keep_their_own_detail() -> None:
    with pytest.raises(RuntimeError) as caught:
        svc.list_phone_numbers(_rejecting_client(500))

    message = str(caught.value)
    assert "rejected your credentials" not in message
    assert "500" in message


def test_domain_name_is_stable_and_scoped_to_the_account() -> None:
    name = svc.sip_domain_name(ACCOUNT_SID)

    assert name == svc.sip_domain_name(ACCOUNT_SID)
    assert name.endswith(".sip.twilio.com")
    assert name == name.lower()


def test_first_run_provisions_domain_credential_and_mapping() -> None:
    client = FakeTwilio()

    endpoint = svc.ensure_sip_endpoint(client)

    assert endpoint.domain == svc.sip_domain_name(ACCOUNT_SID)
    assert endpoint.uri == f"sip:{svc.SIP_USERNAME}@{endpoint.domain}"
    assert client.log == [
        "domain.create",
        "credential_list.create",
        "credential.create:wiretap",
        "mapping.create",
    ]


def test_second_run_creates_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(svc.SIP_PASSWORD_ENV, "KnownPassword123")
    client = _provisioned()

    endpoint = svc.ensure_sip_endpoint(client)

    assert endpoint.password == "KnownPassword123"
    assert client.log == []


def test_lost_local_password_rotates_the_credential() -> None:
    """Twilio never discloses a stored password, so an unknown one is unusable."""
    client = _provisioned()

    endpoint = svc.ensure_sip_endpoint(client)

    assert client.log == ["credential.update"]
    assert endpoint.password != "old"
    assert len(endpoint.password) >= 12


def test_registration_is_enabled_on_a_pre_existing_domain() -> None:
    client = _provisioned()
    client._domains[0].sip_registration = False

    svc.ensure_sip_endpoint(client)

    assert "domain.update" in client.log
    assert client._domains[0].sip_registration is True


def test_generated_password_satisfies_twilio_policy() -> None:
    password = svc.generate_sip_password()

    assert len(password) >= 12
    assert any(c.islower() for c in password)
    assert any(c.isupper() for c in password)
    assert any(c.isdigit() for c in password)


def test_list_phone_numbers_returns_sorted_pairs() -> None:
    client = FakeTwilio(
        numbers=[
            _Record(phone_number="+14155550199", friendly_name="Support"),
            _Record(phone_number="+14155550123", friendly_name="Sales"),
        ]
    )

    assert svc.list_phone_numbers(client) == [
        {"phone_number": "+14155550123", "friendly_name": "Sales"},
        {"phone_number": "+14155550199", "friendly_name": "Support"},
    ]


def test_number_listing_is_paged_rather_than_exhaustive() -> None:
    """A real account can hold thousands; paging every one costs a minute."""
    client = FakeTwilio(
        numbers=[
            _Record(phone_number=f"+1415555{i:04d}", friendly_name="")
            for i in range(500)
        ]
    )

    numbers = svc.list_phone_numbers(client)

    assert len(numbers) == svc.NUMBER_PAGE_SIZE
    assert client.incoming_phone_numbers.queries[0]["limit"] == svc.NUMBER_PAGE_SIZE


def test_number_search_is_pushed_down_to_twilio() -> None:
    client = FakeTwilio(
        numbers=[
            _Record(phone_number="+14155550123", friendly_name="Sales"),
            _Record(phone_number="+19725550199", friendly_name="Support"),
        ]
    )

    numbers = svc.list_phone_numbers(client, contains="972")

    assert [n["phone_number"] for n in numbers] == ["+19725550199"]
    assert client.incoming_phone_numbers.queries[0]["phone_number"] == "972"


def test_place_bridge_call_dials_sip_and_bridges_to_the_agent() -> None:
    client = FakeTwilio()

    sid = svc.place_bridge_call(
        to_number="+14155550123",
        from_number="+14155550199",
        sip_uri="sip:wiretap@example.sip.twilio.com",
        client=client,
    )

    assert sid == "CA123"
    call = client.created_calls[0]
    assert call["to"] == "sip:wiretap@example.sip.twilio.com"
    assert call["from_"] == "+14155550199"
    assert "<Number>+14155550123</Number>" in call["twiml"]
    assert 'answerOnBridge="true"' in call["twiml"]


def test_hangup_never_raises_on_a_dead_call() -> None:
    class Exploding:
        @property
        def calls(self) -> Any:
            raise RuntimeError("gone")

    svc.hangup_call("CA123", Exploding())  # must not raise
    svc.hangup_call("")


def test_hangup_completes_the_leg() -> None:
    client = FakeTwilio()

    svc.hangup_call("CA123", client)

    assert client.completed_calls == ["CA123:completed"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+14155550123", "+14155550123"),
        (" +1 (415) 555-0123 ", "+14155550123"),
        ("+91-9876543210", "+919876543210"),
    ],
)
def test_normalize_e164_accepts_common_formatting(raw: str, expected: str) -> None:
    assert svc.normalize_e164(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "4155550123", "+0123", "not-a-number"])
def test_normalize_e164_rejects_undialable_input(raw: str | None) -> None:
    with pytest.raises(ValueError, match="E.164"):
        svc.normalize_e164(raw)


def test_twiml_cannot_be_injected_through_a_phone_number() -> None:
    with pytest.raises(ValueError, match="E.164"):
        svc.bridge_twiml('+1415555012"/><Hangup/><Dial>', "+14155550199")


def test_from_number_round_trips_through_the_settings_file(tmp_path: Path) -> None:
    assert svc.saved_from_number() is None

    svc.save_from_number(" +1 415-555-0123 ")

    assert svc.saved_from_number() == "+14155550123"
    assert svc.settings_path().is_file()


def test_saved_from_number_survives_a_corrupt_settings_file() -> None:
    path = svc.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    assert svc.saved_from_number() is None

    svc.save_from_number("+14155550123")

    assert svc.saved_from_number() == "+14155550123"


def test_env_from_number_wins_over_the_saved_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    svc.save_from_number("+14155550123")
    monkeypatch.setenv(svc.FROM_NUMBER_ENV, "+14155550199")

    assert svc.resolve_from_number() == "+14155550199"
