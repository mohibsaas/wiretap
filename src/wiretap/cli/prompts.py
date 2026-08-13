"""Interactive CLI helpers — TTY-aware secret / caller setup.

Reuse onboard services; never echo secret values.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich import print

from wiretap.cli import style as ui
from wiretap.providers.catalog import (
    env_for_provider,
    llm_providers,
    provider_catalog,
    stt_providers,
    tts_providers,
)
from wiretap.services.onboard import configure_caller, load_onboard_state, onboard_status
from wiretap.services.secrets import key_status, upsert_secrets

# Platforms → env var for live API key
PLATFORM_API_KEYS: dict[str, str] = {
    "retell": "RETELL_API_KEY",
    "vapi": "VAPI_API_KEY",
    "bland": "BLAND_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "synthflow": "SYNTHFLOW_API_KEY",
    "bolna": "BOLNA_API_KEY",
    "livekit": "LIVEKIT_API_KEY",
}


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def require_interactive(action: str) -> None:
    if not is_interactive():
        print(
            f"[red]Missing credentials for[/red] {action}. "
            "Set them in .env or run [bold]wiretap init[/bold] in a terminal."
        )
        raise typer.Exit(1)


def ensure_env_key(
    env_name: str,
    *,
    label: str | None = None,
    cwd: Path | None = None,
    api_key: str | None = None,
) -> bool:
    """Ensure ``env_name`` is set. Prompt when interactive; return True if available."""
    if api_key and api_key.strip():
        upsert_secrets({env_name: api_key.strip()}, cwd)
        return True

    keys = key_status(cwd)
    if keys.get(env_name):
        return True

    if not is_interactive():
        print(
            f"[red]Missing[/red] {env_name}. "
            f"Export it, add to .env, or run [bold]wiretap init[/bold]."
        )
        raise typer.Exit(1)

    shown = label or env_name
    ui.warn(f"{shown} is not set.")
    value = typer.prompt(f"Enter {env_name}", hide_input=True).strip()
    if not value:
        ui.err(f"Aborted — {env_name} required")
        raise typer.Exit(1)
    upsert_secrets({env_name: value}, cwd)
    ui.ok(f"Saved [bold]{env_name}[/bold] to .env")
    return True


def ensure_platform_key(
    platform: str,
    *,
    cwd: Path | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> None:
    """Ensure platform API key (and LiveKit secret when needed)."""
    plat = platform.lower().strip()
    env_name = PLATFORM_API_KEYS.get(plat)
    if not env_name:
        return
    ensure_env_key(env_name, label=f"{plat} API key", cwd=cwd, api_key=api_key)

    if plat == "livekit":
        keys = key_status(cwd)
        if keys.get("LIVEKIT_TOKEN"):
            return
        if not keys.get("LIVEKIT_API_SECRET"):
            ensure_env_key(
                "LIVEKIT_API_SECRET",
                label="LiveKit API secret",
                cwd=cwd,
                api_key=api_secret,
            )


def ensure_caller_configured(
    *,
    cwd: Path | None = None,
    force: bool = False,
) -> None:
    """Ensure test-agent LLM/STT/TTS is configured (interactive wizard if needed)."""
    status = onboard_status(cwd)
    if status.get("caller_configured") and not force:
        # Still verify keys exist for the chosen providers
        caller = status.get("caller") or {}
        keys = key_status(cwd)
        llm = str(caller.get("llm_provider") or "openai")
        stt = str(caller.get("stt") or "pyai")
        tts = str(caller.get("tts") or "pyai")
        missing = []
        for pid in (llm, stt, tts):
            env = env_for_provider(pid)
            if not keys.get(env):
                missing.append(env)
        if not missing:
            return
        ui.warn(f"Caller configured but missing keys: {', '.join(missing)}")

    if not is_interactive():
        ui.err("Test agent not configured.")
        ui.muted("Run wiretap init or set LLM/STT/TTS keys in .env.")
        raise typer.Exit(1)

    configure_caller_interactive(cwd=cwd)


def configure_caller_interactive(*, cwd: Path | None = None) -> dict:
    """Prompt for LLM / STT / TTS and write via configure_caller."""
    with ui.spinner("Loading provider catalog…"):
        catalog = provider_catalog()
        llm_ids = [p.id for p in llm_providers()]
        stt_ids = [p.id for p in stt_providers()]
        tts_ids = [p.id for p in tts_providers()]
    defaults = catalog.get("defaults") or {}
    state = load_onboard_state(cwd)
    keys = key_status(cwd)

    ui.info("Configure LLM + speech for the simulated caller")

    # Keep the list readable — top common providers first, then rest
    preferred = ["openai", "anthropic", "gemini", "groq", "openrouter", "mistral"]
    llm_choices = [p for p in preferred if p in llm_ids]
    llm_choices += [p for p in llm_ids if p not in llm_choices][:20]

    llm = _pick(
        "LLM provider",
        llm_choices,
        default=str(state.get("llm_provider") or defaults.get("llm") or "openai"),
    )
    llm_env = env_for_provider(llm)
    llm_key = None
    if keys.get(llm_env):
        ui.muted(f"Using existing {llm_env}")
    else:
        llm_key = typer.prompt(f"{llm_env}", hide_input=True).strip() or None

    llm_info = next((p for p in llm_providers() if p.id == llm), None)
    default_model = (
        str(state.get("simulator_model") or "")
        or (llm_info.default_model if llm_info else None)
        or "gpt-4o-mini"
    )
    simulator = typer.prompt("Simulator model", default=default_model).strip()
    judge = typer.prompt("Judge model", default=simulator).strip()

    stt = _pick(
        "STT provider",
        stt_ids,
        default=str(state.get("stt") or defaults.get("stt") or "pyai"),
    )
    tts = _pick(
        "TTS provider",
        tts_ids,
        default=str(state.get("tts") or defaults.get("tts") or "pyai"),
    )
    voice = typer.prompt(
        "TTS voice id",
        default=str(state.get("voice") or defaults.get("voice") or "alloy"),
    ).strip()

    stt_key = None
    tts_key = None
    stt_env = env_for_provider(stt)
    tts_env = env_for_provider(tts)
    if not keys.get(stt_env) and stt_env != llm_env:
        stt_key = typer.prompt(f"{stt_env} (STT)", hide_input=True).strip() or None
    elif keys.get(stt_env):
        ui.muted(f"Using existing {stt_env} for STT")
    if not keys.get(tts_env) and tts_env not in {llm_env, stt_env}:
        tts_key = typer.prompt(f"{tts_env} (TTS)", hide_input=True).strip() or None
    elif keys.get(tts_env):
        ui.muted(f"Using existing {tts_env} for TTS")

    result = configure_caller(
        llm_provider=llm,
        llm_api_key=llm_key,
        simulator_model=simulator,
        judge_model=judge,
        stt=stt,
        tts=tts,
        voice=voice,
        stt_api_key=stt_key,
        tts_api_key=tts_key,
        cwd=cwd,
    )
    ui.ok(
        f"Test agent configured  "
        f"[{ui.ACCENT}]{llm}[/{ui.ACCENT}] · "
        f"[{ui.ACCENT}]{stt}[/{ui.ACCENT}] STT · "
        f"[{ui.ACCENT}]{tts}[/{ui.ACCENT}] TTS"
    )
    return result


def _pick(label: str, choices: list[str], *, default: str) -> str:
    if default not in choices and choices:
        default = choices[0]
    # Compact list for common sizes
    if len(choices) <= 12:
        shown = " · ".join(
            f"[bold {ui.ACCENT}]{c}[/bold {ui.ACCENT}]"
            if c == default
            else f"[{ui.MUTED}]{c}[/{ui.MUTED}]"
            for c in choices
        )
        print(f"[{ui.MUTED}]{label}:[/{ui.MUTED}] {shown}")
    else:
        head = " · ".join(f"[{ui.MUTED}]{c}[/{ui.MUTED}]" for c in choices[:8])
        print(f"[{ui.MUTED}]{label} (common):[/{ui.MUTED}] {head} …")
    raw = typer.prompt(label, default=default).strip().lower()
    if raw not in choices:
        ui.warn(f"Unknown {label} {raw!r} — using {default}")
        return default
    return raw


def print_status(*, cwd: Path | None = None) -> None:
    """Show configuration status without secret values."""
    from rich.text import Text

    from wiretap.paths import wiretap_root
    from wiretap.services.secrets import env_file, key_report

    with ui.spinner("Loading status…"):
        # Skip LiteLLM provider catalog — not shown in CLI status.
        status = onboard_status(cwd, include_providers=False)
        report = key_report(cwd)
    caller = status.get("caller") or {}

    def val(text: object, *, empty: str = "—") -> Text:
        bit = str(text or "").strip()
        if not bit or bit == "None":
            return Text(empty, style=ui.MUTED)
        return Text(bit, style=ui.ACCENT)

    agent_state = (
        Text("configured", style=f"bold {ui.OK}")
        if status.get("caller_configured")
        else Text("not configured", style=f"bold {ui.WARN}")
    )
    secrets_path = env_file(cwd)
    secrets_label = Text(str(secrets_path), style=ui.MUTED)
    if not report.get("wiretap_env_exists"):
        secrets_label.append("  (missing)", style=ui.WARN)

    rows: list[tuple[str, Text]] = [
        ("Data dir", Text(str(wiretap_root(cwd)), style=ui.MUTED)),
        ("Secrets file", secrets_label),
        ("Test agent", agent_state),
        ("LLM", val(caller.get("llm_provider"))),
        ("Simulator", val(caller.get("simulator_model"))),
        ("Judge", val(caller.get("judge_model"))),
        ("STT", val(caller.get("stt"))),
        ("TTS", val(caller.get("tts"))),
        ("Voice", val(caller.get("voice"))),
        ("Platform", val(status.get("platform"))),
        ("Agent", val(status.get("agent_id"))),
        ("Suite", val(status.get("suite_name"))),
        ("Suites on disk", val(status.get("suite_count") or 0, empty="0")),
    ]
    ui.console.print()
    ui.status_table(rows=rows)

    detail = report.get("keys") or {}
    by_source: dict[str, list[str]] = {
        "wiretap": [],
        "project": [],
        "legacy": [],
        "environ": [],
    }
    for key, meta in detail.items():
        if not meta.get("set"):
            continue
        for src in meta.get("sources") or []:
            if src in by_source:
                by_source[src].append(key)

    def _print_key_group(label: str, names: list[str], *, style: str = ui.OK) -> None:
        if not names:
            return
        line = Text()
        line.append(f"{label} ", style=ui.MUTED)
        line.append(f"({len(names)}): ", style=ui.MUTED)
        for i, k in enumerate(sorted(names)):
            if i:
                line.append(" · ", style=ui.MUTED)
            line.append(k, style=style)
        ui.console.print(line)

    if by_source["wiretap"]:
        _print_key_group("Keys in wiretap store", by_source["wiretap"])
    else:
        ui.muted("Keys in wiretap store: (none)")

    project_env = report.get("project_env")
    if project_env and by_source["project"]:
        ui.muted(f"Also in project .env ({project_env}):")
        line = Text("  ")
        for i, k in enumerate(sorted(by_source["project"])):
            if i:
                line.append(" · ", style=ui.MUTED)
            line.append(k, style=ui.WARN)
        ui.console.print(line)
        ui.muted("  (migration fallback — not removed by deleting ~/.wiretap)")
    elif project_env:
        ui.muted(f"Project .env present ({project_env}) — no managed keys in it")

    legacy_env = report.get("legacy_env")
    if legacy_env and by_source["legacy"]:
        ui.muted(f"Also in legacy .wiretap/.env ({legacy_env}):")
        line = Text("  ")
        for i, k in enumerate(sorted(by_source["legacy"])):
            if i:
                line.append(" · ", style=ui.MUTED)
            line.append(k, style=ui.WARN)
        ui.console.print(line)

    if by_source["environ"]:
        ui.muted("Also in process environment:")
        line = Text("  ")
        for i, k in enumerate(sorted(by_source["environ"])):
            if i:
                line.append(" · ", style=ui.MUTED)
            line.append(k, style=ui.WARN)
        ui.console.print(line)

    if not any(by_source.values()):
        ui.warn("No managed API keys found")

__all__ = [
    "PLATFORM_API_KEYS",
    "configure_caller_interactive",
    "ensure_caller_configured",
    "ensure_env_key",
    "ensure_platform_key",
    "is_interactive",
    "print_status",
    "require_interactive",
]
