"""Read secrets from the environment — never from suite YAML."""

from __future__ import annotations

import os


def require_env(name: str) -> str:
    """Return a required secret, reloading dotenv files first."""
    # Keep runtime in sync with ~/.wiretap/.env (and migration fallbacks) even
    # when the UI/CLI process started before keys were written.
    from wiretap.services.secrets import load_dotenv

    load_dotenv()
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(
            f"Missing environment variable {name}. "
            "Set it via `wiretap init`, your shell, or .env (never commit secrets)."
        )
    return value
