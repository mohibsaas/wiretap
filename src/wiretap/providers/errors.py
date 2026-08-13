"""Map provider catalog HTTP failures to safe, user-facing messages.

Never includes secret values in returned strings.
"""

from __future__ import annotations


def is_auth_error(error: str | None) -> bool:
    """True when the vendor rejected the API key (401/403)."""
    code = (error or "").strip().lower()
    if not code:
        return False
    if code in {"http_401", "http_403", "unauthorized", "forbidden"}:
        return True
    # Tolerate bare status codes from older call sites
    return code in {"401", "403"}


def catalog_error_message(
    error: str | None,
    *,
    env_name: str,
    what: str = "catalog",
) -> str:
    """Human-readable reason for a failed live catalog fetch (no secrets)."""
    code = (error or "").strip() or "unavailable"
    if is_auth_error(code):
        status = "401" if "401" in code else "403" if "403" in code else "401/403"
        return (
            f"{env_name} was rejected by the provider (HTTP {status}). "
            "The key is missing, revoked, or lacks access."
        )
    if code == "no_api_key":
        return f"{env_name} is not set."
    if code == "timeout":
        return f"Timed out loading {what}."
    if code == "empty_response":
        return f"Provider returned an empty {what}."
    if code == "not_supported":
        return f"Live {what} is not supported for this provider."
    if code.startswith("http_"):
        return f"Provider error loading {what} ({code.replace('_', ' ')})."
    return f"Could not load live {what} ({code})."


__all__ = ["catalog_error_message", "is_auth_error"]
