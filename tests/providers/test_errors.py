"""Provider catalog error mapping."""

from __future__ import annotations

from wiretap.providers.errors import catalog_error_message, is_auth_error


def test_is_auth_error() -> None:
    assert is_auth_error("http_401")
    assert is_auth_error("http_403")
    assert is_auth_error("401")
    assert not is_auth_error("http_500")
    assert not is_auth_error("timeout")
    assert not is_auth_error(None)


def test_catalog_error_message_auth() -> None:
    msg = catalog_error_message("http_401", env_name="OPENAI_API_KEY", what="models")
    assert "OPENAI_API_KEY" in msg
    assert "401" in msg
    assert "sk-" not in msg


def test_catalog_error_message_other() -> None:
    msg = catalog_error_message("timeout", env_name="OPENAI_API_KEY", what="models")
    assert "Timed out" in msg
