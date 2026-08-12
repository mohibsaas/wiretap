"""Read secrets from the environment — never from suite YAML."""

from __future__ import annotations

import os


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing environment variable {name}. "
            "Set it in your shell or .env (never commit secrets)."
        )
    return value
