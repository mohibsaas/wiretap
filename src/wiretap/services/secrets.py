"""Local .env secret upsert — never return secret values."""

from __future__ import annotations

import os
import re
from pathlib import Path

from wiretap.providers.catalog import managed_secret_keys

_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,64}$")


def _allowed_keys() -> set[str]:
    return set(managed_secret_keys())


# Back-compat: prefer managed_secret_keys() — do not compute at import time.
MANAGED_KEYS: tuple[str, ...] = ()


def env_file(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()) / ".env"


def load_dotenv(cwd: Path | None = None) -> None:
    """Load cwd/.env into os.environ. Does not override vars already set."""
    for key, val in _load_dotenv_map(env_file(cwd)).items():
        if key and val and key not in os.environ:
            os.environ[key] = val


def key_status(cwd: Path | None = None) -> dict[str, bool]:
    """Return which managed keys are set (bool only)."""
    root = cwd or Path.cwd()
    load_dotenv(root)
    merged = _load_dotenv_map(env_file(root))
    out: dict[str, bool] = {}
    for key in managed_secret_keys():
        val = (os.environ.get(key) or merged.get(key) or "").strip()
        out[key] = bool(val)
    return out


def upsert_secrets(
    secrets: dict[str, str],
    cwd: Path | None = None,
) -> list[str]:
    """Write non-empty secrets into .env and os.environ. Returns keys updated."""
    root = cwd or Path.cwd()
    path = env_file(root)
    updated: list[str] = []
    current = _load_dotenv_map(path)
    allowed = _allowed_keys()

    for raw_key, raw_val in secrets.items():
        key = (raw_key or "").strip().upper()
        if key not in allowed:
            raise ValueError(f"Unsupported key: {key}")
        if not _KEY_RE.match(key):
            raise ValueError(f"Invalid key name: {key}")
        val = (raw_val or "").strip()
        if not val:
            continue
        if len(val) > 8_192:
            raise ValueError(f"Value too long for {key}")
        current[key] = val
        os.environ[key] = val
        updated.append(key)

    if updated:
        _write_dotenv(path, current)
    return updated


def _load_dotenv_map(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.is_file():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            data[k] = v
    return data


def _write_dotenv(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_dotenv_map(path) if path.is_file() else {}
    existing.update(data)
    lines = [
        "# Local secrets for wiretap — never commit this file.",
        "# Managed by `wiretap ui` onboarding. Values are not returned by the API.",
        "",
    ]
    for key in sorted(existing):
        val = existing[key].replace("\n", "").replace("\r", "")
        lines.append(f"{key}={val}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


__all__ = ["MANAGED_KEYS", "env_file", "key_status", "load_dotenv", "upsert_secrets"]
