"""Local .wiretap/ layout helpers."""

from __future__ import annotations

from pathlib import Path

ROOT_DIRNAME = ".wiretap"
SUITES_DIRNAME = "suites"
SIMULATIONS_DIRNAME = "simulations"
# Legacy on-disk name (pre-rename); still read for back-compat
RUNS_DIRNAME = "runs"
GRAPHS_DIRNAME = "graphs"


def wiretap_root(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()) / ROOT_DIRNAME


def suites_dir(cwd: Path | None = None) -> Path:
    return wiretap_root(cwd) / SUITES_DIRNAME


def simulations_dir(cwd: Path | None = None) -> Path:
    return wiretap_root(cwd) / SIMULATIONS_DIRNAME


def graphs_dir(cwd: Path | None = None) -> Path:
    return wiretap_root(cwd) / GRAPHS_DIRNAME


def ensure_layout(cwd: Path | None = None) -> Path:
    root = wiretap_root(cwd)
    (root / SUITES_DIRNAME).mkdir(parents=True, exist_ok=True)
    (root / SIMULATIONS_DIRNAME).mkdir(parents=True, exist_ok=True)
    (root / GRAPHS_DIRNAME).mkdir(parents=True, exist_ok=True)
    return root


def suite_path(name: str, cwd: Path | None = None) -> Path:
    """Resolve suite name or path to a YAML file."""
    raw = Path(name)
    if raw.suffix in {".yaml", ".yml"} and (raw.is_file() or raw.is_absolute()):
        return raw
    if raw.is_file():
        return raw
    stem = raw.stem if raw.suffix in {".yaml", ".yml"} else name
    return suites_dir(cwd) / f"{stem}.yaml"


def simulation_artifact_dirs(cwd: Path | None = None) -> list[Path]:
    """Dirs that may contain simulation jsonl (new + legacy)."""
    root = wiretap_root(cwd)
    dirs: list[Path] = []
    primary = root / SIMULATIONS_DIRNAME
    legacy = root / RUNS_DIRNAME
    if primary.is_dir():
        dirs.append(primary)
    if legacy.is_dir() and legacy.resolve() != primary.resolve():
        dirs.append(legacy)
    return dirs


__all__ = [
    "GRAPHS_DIRNAME",
    "ROOT_DIRNAME",
    "RUNS_DIRNAME",
    "SIMULATIONS_DIRNAME",
    "SUITES_DIRNAME",
    "ensure_layout",
    "graphs_dir",
    "simulation_artifact_dirs",
    "simulations_dir",
    "suite_path",
    "suites_dir",
    "wiretap_root",
]
