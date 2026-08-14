"""Apply a different live-agent target onto a suite at run time.

Suites embed one default ``agent:`` block. Overrides let you reuse the same
scenarios against another agent without rewriting YAML.
"""

from __future__ import annotations

from pathlib import Path

from wiretap.models import SuiteConfig, TransportKind
from wiretap.paths import suite_path
from wiretap.suite.loader import load_suite

# The run-time question is "web or phone", not a transport-kind quiz.
_PHONE_WORDS = {"phone", "pstn", "call", "dial"}
_WEB_WORDS = {"web", "online", "webrtc"}


def resolve_transport_choice(raw: str, *, current: str) -> str:
    """Map a user's word (or a literal transport kind) onto a TransportKind value.

    Raises ``ValueError`` for anything unrecognised, so the CLI and the API can
    each report it their own way.
    """
    value = (raw or "").strip().lower()
    if value in _PHONE_WORDS:
        return TransportKind.PSTN.value
    if value in _WEB_WORDS:
        # "web" means "however this suite normally connects", unless that is
        # itself the phone — then there is nothing to fall back to but webrtc.
        return TransportKind.WEBRTC.value if current == "pstn" else current
    return TransportKind(value).value


def with_agent_override(
    suite: SuiteConfig,
    *,
    agent_id: str | None = None,
    platform: str | None = None,
    token_env: str | None = None,
    transport: str | None = None,
    phone_number: str | None = None,
    agent_from: str | None = None,
    cwd: Path | None = None,
) -> SuiteConfig:
    """Return a deep copy of ``suite`` with agent fields overridden.

    ``agent_from`` copies the full agent target from another local suite name/path.
    Explicit ``agent_id`` / ``platform`` / ``token_env`` / ``transport`` /
    ``phone_number`` win after that.
    """
    out = suite.model_copy(deep=True)
    if agent_from:
        other = load_suite(suite_path(agent_from, cwd))
        out.agent = other.agent.model_copy(deep=True)
    if platform is not None and str(platform).strip():
        out.agent.platform = str(platform).strip().lower()
        if not token_env and out.agent.platform in {"retell", "vapi", "bland"}:
            out.agent.token_env = f"{out.agent.platform.upper()}_API_KEY"
    if agent_id is not None and str(agent_id).strip():
        out.agent.agent_id = str(agent_id).strip()
    if token_env is not None and str(token_env).strip():
        out.agent.token_env = str(token_env).strip()
    if transport is not None and str(transport).strip():
        try:
            out.agent.transport = TransportKind(str(transport).strip().lower())
        except ValueError:
            pass
    if phone_number is not None and str(phone_number).strip():
        out.agent.phone_number = str(phone_number).strip()
    return out


__all__ = ["resolve_transport_choice", "with_agent_override"]
