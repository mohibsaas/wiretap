"""Secret store — ``~/.wiretap/.env`` by default (never return secret values)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from wiretap.paths import ensure_layout, wiretap_root
from wiretap.providers.catalog import managed_secret_keys

_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,64}$")


def _allowed_keys() -> set[str]:
    return set(managed_secret_keys())


# Back-compat: prefer managed_secret_keys() — do not compute at import time.
MANAGED_KEYS: tuple[str, ...] = ()


def env_file(cwd: Path | None = None) -> Path:
    """Path to the dotenv file wiretap reads/writes.

    - Explicit ``cwd`` (tests): ``{cwd}/.env``
    - Default: ``{wiretap_root}/.env`` (usually ``~/.wiretap/.env``)
    """
    if cwd is not None:
        return Path(cwd) / ".env"
    return wiretap_root(None) / ".env"


def project_env_file(cwd: Path | None = None) -> Path | None:
    """Optional project ``./.env`` used as a migration fallback (read-only)."""
    if cwd is not None:
        return None
    local = Path.cwd() / ".env"
    return _as_extra_env(local, primary=env_file(None))


def legacy_env_file(cwd: Path | None = None) -> Path | None:
    """Pre-global-home store: ``{cwd}/.wiretap/.env`` (read-only migration)."""
    root = Path.cwd() if cwd is None else Path(cwd)
    legacy = root / ".wiretap" / ".env"
    return _as_extra_env(legacy, primary=env_file(cwd))


def _as_extra_env(path: Path, *, primary: Path) -> Path | None:
    if not path.is_file():
        return None
    try:
        if path.resolve() == primary.resolve():
            return None
    except OSError:
        pass
    return path


def _dotenv_candidates(cwd: Path | None = None) -> list[Path]:
    """Files to load: primary store, then migration fallbacks."""
    primary = env_file(cwd)
    out = [primary]
    for extra in (project_env_file(cwd), legacy_env_file(cwd)):
        if extra is not None and extra not in out:
            out.append(extra)
    return out


def load_dotenv(cwd: Path | None = None) -> None:
    """Load dotenv into os.environ.

    Does not override non-empty vars already set in the process environment.
    Empty / missing vars are filled from files (primary, then project, then legacy).
    """
    for path in _dotenv_candidates(cwd):
        for key, val in _load_dotenv_map(path).items():
            if not key or not val:
                continue
            if (os.environ.get(key) or "").strip():
                continue
            os.environ[key] = val


def key_status(cwd: Path | None = None) -> dict[str, bool]:
    """Return which managed keys are set (bool only).

    A key counts as set if present in the wiretap store, project/legacy ``.env``,
    or the process environment.
    """
    report = key_report(cwd)
    return {key: meta["set"] for key, meta in report["keys"].items()}


def key_report(cwd: Path | None = None) -> dict[str, Any]:
    """Presence + source attribution for managed keys (never values).

    Sources per key (subset):
    - ``wiretap`` — primary ``~/.wiretap/.env`` (or ``{cwd}/.env`` in tests)
    - ``project`` — cwd ``./.env`` migration fallback
    - ``legacy`` — ``{cwd}/.wiretap/.env`` (pre-global-home layout)
    - ``environ`` — process env only (not in any file)
    """
    primary = env_file(cwd)
    primary_map = _load_dotenv_map(primary)
    project = project_env_file(cwd)
    project_map = _load_dotenv_map(project) if project is not None else {}
    legacy = legacy_env_file(cwd)
    legacy_map = _load_dotenv_map(legacy) if legacy is not None else {}

    # Attribute file sources, then ensure process env is hydrated for runtime.
    detail: dict[str, dict[str, Any]] = {}
    for key in managed_secret_keys():
        sources: list[str] = []
        if (primary_map.get(key) or "").strip():
            sources.append("wiretap")
        if (project_map.get(key) or "").strip():
            sources.append("project")
        if (legacy_map.get(key) or "").strip():
            sources.append("legacy")
        in_env = bool((os.environ.get(key) or "").strip())
        if in_env and not sources:
            sources.append("environ")
        detail[key] = {"set": bool(sources), "sources": sources}

    load_dotenv(cwd)

    return {
        "wiretap_env": str(primary),
        "wiretap_env_exists": primary.is_file(),
        "project_env": str(project) if project is not None else None,
        "legacy_env": str(legacy) if legacy is not None else None,
        "keys": detail,
    }


def upsert_secrets(
    secrets: dict[str, str],
    cwd: Path | None = None,
) -> list[str]:
    """Write non-empty secrets into .env and os.environ. Returns keys updated."""
    path = env_file(cwd)
    if cwd is None:
        ensure_layout(None)
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
        # Support `export KEY=value` and optional quotes.
        if k.lower().startswith("export "):
            k = k[7:].strip()
        v = v.strip().strip('"').strip("'")
        if k:
            data[k] = v
    return data


def _write_dotenv(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_dotenv_map(path) if path.is_file() else {}
    existing.update(data)
    lines = [
        "# Wiretap secrets — never commit this file.",
        "# Managed by `wiretap init` / `wiretap ui`. Values are not returned by the API.",
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


__all__ = [
    "MANAGED_KEYS",
    "env_file",
    "key_report",
    "key_status",
    "legacy_env_file",
    "load_dotenv",
    "project_env_file",
    "upsert_secrets",
]
