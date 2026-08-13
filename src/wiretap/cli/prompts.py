"""Interactive CLI helpers — TTY-aware secret / caller setup.

Reuse onboard services; never echo secret values.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich import print

from wiretap.cli.pick import pick_option
from wiretap.cli import style as ui
from wiretap.providers.catalog import (
    default_voice_for,
    env_for_provider,
    llm_providers,
    provider_catalog,
    stt_providers,
    tts_providers,
)
from wiretap.providers.model_catalog import resolve_llm_models
from wiretap.providers.voice_catalog import resolve_tts_voices
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
        ui.err("Simulator not configured.")
        ui.muted("Run wiretap init or wiretap simulator configure.")
        raise typer.Exit(1)

    configure_caller_interactive(cwd=cwd)


def configure_caller_interactive(
    *,
    cwd: Path | None = None,
    sections: set[str] | None = None,
) -> dict:
    """Prompt for LLM / STT / TTS and write via configure_caller.

    ``sections`` limits what to ask (e.g. ``{"models"}``, ``{"tts"}``).
    ``None`` or ``{"all"}`` runs the full wizard (used by ``wiretap init``).
    """
    with ui.spinner("Loading provider catalog…"):
        catalog = provider_catalog()
        llm_ids = [p.id for p in llm_providers()]
        stt_ids = [p.id for p in stt_providers()]
        tts_ids = [p.id for p in tts_providers()]
    defaults = catalog.get("defaults") or {}
    state = load_onboard_state(cwd)
    keys = key_status(cwd)

    want = sections or {"all"}
    do_all = "all" in want
    do_llm = do_all or "llm" in want
    do_models = do_all or do_llm or "models" in want
    do_stt = do_all or "speech" in want or "stt" in want
    do_tts = do_all or "speech" in want or "tts" in want

    # Start from current config so partial updates don't wipe other fields.
    llm = str(state.get("llm_provider") or defaults.get("llm") or "openai")
    simulator = str(state.get("simulator_model") or "gpt-4o-mini")
    judge = str(state.get("judge_model") or simulator)
    stt = str(state.get("stt") or defaults.get("stt") or "pyai")
    tts = str(state.get("tts") or defaults.get("tts") or "pyai")
    voice = str(state.get("voice") or default_voice_for(tts))
    llm_key: str | None = None
    stt_key: str | None = None
    tts_key: str | None = None

    title = (
        "Configure LLM + speech for the simulator"
        if do_all
        else "Update simulator"
    )
    with ui.timeline(title) as rail:
        if do_llm or do_models:
            rail.group("LLM")

        if do_llm:
            preferred = [
                "openai",
                "anthropic",
                "gemini",
                "groq",
                "openrouter",
                "mistral",
            ]
            llm_choices = [p for p in preferred if p in llm_ids]
            llm_choices += [p for p in llm_ids if p not in llm_choices][:20]
            llm = _pick(
                "LLM provider",
                llm_choices,
                default=llm,
            )
            llm_env = env_for_provider(llm)
            if keys.get(llm_env):
                ui.muted(f"Using existing {llm_env}")
            else:
                llm_key = (
                    typer.prompt(f"{llm_env}", hide_input=True).strip() or None
                )
        else:
            llm_env = env_for_provider(llm)

        if do_models:
            resolved_models, llm_key = _resolve_models_with_key_retry(
                llm,
                llm_env=llm_env,
                api_key=llm_key,
                cwd=cwd,
            )
            model_choices = list(resolved_models.get("models") or [])
            default_model = (
                simulator
                or str(resolved_models.get("default_model") or "")
                or (model_choices[0] if model_choices else "gpt-4o-mini")
            )
            if default_model not in model_choices and model_choices:
                if simulator.strip():
                    model_choices = [
                        default_model,
                        *[m for m in model_choices if m != default_model],
                    ]
                else:
                    default_model = str(
                        resolved_models.get("default_model") or model_choices[0]
                    )
            if resolved_models.get("source") == "live":
                ui.rail_text(
                    f"[{ui.ACCENT}]•[/{ui.ACCENT}] Found {len(model_choices)} models"
                )
            elif resolved_models.get("live_supported"):
                from wiretap.providers.errors import (
                    catalog_error_message,
                    is_auth_error,
                )

                reason = resolved_models.get("error") or "unavailable"
                if not is_auth_error(str(reason)):
                    ui.muted(
                        catalog_error_message(
                            str(reason), env_name=llm_env, what="models"
                        )
                        + " — using curated list."
                    )

            simulator = _pick(
                "Simulator model",
                model_choices,
                default=default_model,
                normalize=None,
                allow_custom=True,
            )
            judge = _pick(
                "Judge model",
                model_choices,
                default=judge if judge in model_choices else simulator,
                normalize=None,
                allow_custom=True,
            )

        if do_stt or do_tts:
            rail.group("Speech")

        if do_stt:
            stt = _pick(
                "STT provider",
                stt_ids,
                default=stt,
            )
            stt_env = env_for_provider(stt)
            if not keys.get(stt_env) and stt_env != llm_env:
                stt_key = (
                    typer.prompt(f"{stt_env} (STT)", hide_input=True).strip() or None
                )
            elif keys.get(stt_env):
                ui.muted(f"Using existing {stt_env} for STT")
        else:
            stt_env = env_for_provider(stt)

        if do_tts:
            tts = _pick(
                "TTS provider",
                tts_ids,
                default=tts,
            )
            tts_env = env_for_provider(tts)
            if not keys.get(tts_env) and tts_env not in {llm_env, stt_env}:
                tts_key = (
                    typer.prompt(f"{tts_env} (TTS)", hide_input=True).strip() or None
                )
            elif keys.get(tts_env):
                ui.muted(f"Using existing {tts_env} for TTS")

            voice_api_key = tts_key
            if not voice_api_key and tts_env == stt_env:
                voice_api_key = stt_key
            if not voice_api_key and tts_env == llm_env:
                voice_api_key = llm_key

            resolved, voice_api_key = _resolve_voices_with_key_retry(
                tts,
                tts_env=tts_env,
                api_key=voice_api_key,
                cwd=cwd,
            )
            if voice_api_key and tts_env not in {llm_env, stt_env}:
                tts_key = voice_api_key
            elif voice_api_key and tts_env == stt_env and stt_env != llm_env:
                stt_key = voice_api_key
            elif voice_api_key and tts_env == llm_env:
                llm_key = voice_api_key

            voice_entries = list(resolved.get("voices") or [])
            voice_ids = [v["id"] for v in voice_entries]
            default_voice = (
                voice
                if voice and (not voice_ids or voice in voice_ids)
                else str(resolved.get("default_voice") or default_voice_for(tts))
            )
            if resolved.get("source") == "live":
                ui.rail_text(
                    f"[{ui.ACCENT}]•[/{ui.ACCENT}] Found {len(voice_entries)} voices"
                )
            elif resolved.get("live_supported"):
                from wiretap.providers.errors import (
                    catalog_error_message,
                    is_auth_error,
                )

                reason = resolved.get("error") or "unavailable"
                if not is_auth_error(str(reason)):
                    ui.muted(
                        catalog_error_message(
                            str(reason), env_name=tts_env, what="voices"
                        )
                        + " — using curated list."
                    )

            if voice_ids:
                voice_options = [(v["label"], v["id"]) for v in voice_entries]
                voice = pick_option(
                    "TTS voice",
                    voice_options,
                    default=default_voice,
                    allow_custom=True,
                    custom_prompt="Paste custom voice id",
                )
            else:
                voice = typer.prompt("TTS voice id", default=default_voice).strip()

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
        synced = result.get("suites_synced") or []
        if synced:
            ui.muted(
                "Updated suite YAML speech/models: "
                + ", ".join(synced[:6])
                + ("…" if len(synced) > 6 else "")
            )
        rail.finish(
            f"Simulator configured  "
            f"[{ui.ACCENT}]{llm}[/{ui.ACCENT}] · "
            f"[{ui.ACCENT}]{stt}[/{ui.ACCENT}] STT · "
            f"[{ui.ACCENT}]{tts}[/{ui.ACCENT}] TTS"
        )
    return result


_SIMULATOR_SECTIONS: list[tuple[str, str]] = [
    ("Everything", "all"),
    ("LLM provider + models", "llm"),
    ("Simulator & judge models only", "models"),
    ("STT + TTS + voice", "speech"),
    ("STT only", "stt"),
    ("TTS + voice only", "tts"),
]


def pick_simulator_sections() -> set[str]:
    """Ask which simulator settings to update."""
    choice = pick_option(
        "What do you want to update?",
        _SIMULATOR_SECTIONS,
        default="all",
        allow_custom=False,
    )
    return {choice}


def print_simulator_status(*, cwd: Path | None = None) -> None:
    """Compact simulator-only status (not the full ``wiretap status`` dump)."""
    from rich.text import Text

    status = onboard_status(cwd, include_providers=False)
    caller = status.get("caller") or {}
    configured = bool(status.get("caller_configured"))

    def val(text: object, *, empty: str = "—") -> Text:
        bit = str(text or "").strip()
        if not bit or bit == "None":
            return Text(empty, style=ui.MUTED)
        return Text(bit, style=ui.ACCENT)

    state = (
        Text("configured", style=f"bold {ui.OK}")
        if configured
        else Text("not configured", style=f"bold {ui.WARN}")
    )
    rows: list[tuple[str, Text]] = [
        ("Simulator", state),
        ("LLM", val(caller.get("llm_provider"))),
        ("Simulator model", val(caller.get("simulator_model"))),
        ("Judge model", val(caller.get("judge_model"))),
        ("STT", val(caller.get("stt"))),
        ("TTS", val(caller.get("tts"))),
        ("Voice", val(caller.get("voice"))),
    ]
    ui.console.print()
    ui.status_table(rows=rows, title="simulator")
    ui.console.print()
    ui.next_cmd("wiretap simulator configure", hint="Update")
    ui.next_cmd("wiretap status", hint="Full project status")


def _prompt_new_api_key(env_name: str, *, label: str = "") -> str | None:
    shown = label or env_name
    ui.warn(f"{shown} looks invalid.")
    value = typer.prompt(f"Enter a new {env_name}", hide_input=True).strip()
    return value or None


def _resolve_models_with_key_retry(
    provider: str,
    *,
    llm_env: str,
    api_key: str | None,
    cwd: Path | None,
    attempts: int = 3,
) -> tuple[dict, str | None]:
    """Load models; on 401/403 re-prompt for a new key (up to ``attempts``)."""
    from wiretap.providers.errors import catalog_error_message, is_auth_error

    key = api_key
    resolved: dict = {}
    for i in range(max(1, attempts)):
        with ui.spinner(f"Loading {provider} models…"):
            resolved = resolve_llm_models(provider, api_key=key, cwd=cwd)
        if resolved.get("source") == "live":
            return resolved, key
        err = str(resolved.get("error") or "")
        if not is_auth_error(err):
            return resolved, key
        ui.warn(catalog_error_message(err, env_name=llm_env, what="models"))
        if i >= attempts - 1:
            ui.muted("Continuing with curated models — update the key in .env when ready.")
            break
        key = _prompt_new_api_key(llm_env)
        if not key:
            ui.muted("Continuing with curated models — update the key in .env when ready.")
            break
    return resolved, key


def _resolve_voices_with_key_retry(
    provider: str,
    *,
    tts_env: str,
    api_key: str | None,
    cwd: Path | None,
    attempts: int = 3,
) -> tuple[dict, str | None]:
    """Load voices; on 401/403 re-prompt for a new key (up to ``attempts``)."""
    from wiretap.providers.errors import catalog_error_message, is_auth_error

    key = api_key
    resolved: dict = {}
    for i in range(max(1, attempts)):
        with ui.spinner(f"Loading {provider} voices…"):
            resolved = resolve_tts_voices(provider, api_key=key, cwd=cwd)
        if resolved.get("source") == "live":
            return resolved, key
        err = str(resolved.get("error") or "")
        # No key and live unsupported / curated path — nothing to retry.
        if not resolved.get("live_supported"):
            return resolved, key
        if not is_auth_error(err):
            return resolved, key
        ui.warn(catalog_error_message(err, env_name=tts_env, what="voices"))
        if i >= attempts - 1:
            ui.muted("Continuing with curated voices — update the key in .env when ready.")
            break
        key = _prompt_new_api_key(tts_env, label=f"{tts_env} (TTS)")
        if not key:
            ui.muted("Continuing with curated voices — update the key in .env when ready.")
            break
    return resolved, key


def _pick(
    label: str,
    choices: list[str],
    *,
    default: str,
    normalize=str.lower,
    allow_custom: bool = False,
    show_choices: bool = True,
) -> str:
    """Dropdown picker (↑↓) with optional custom paste."""
    _ = normalize, show_choices  # kept for call-site compatibility
    return pick_option(
        label,
        choices,
        default=default,
        allow_custom=allow_custom or True,
    )


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
        ("Simulator", agent_state),
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

    ui.console.print()
    if status.get("caller_configured"):
        ui.next_cmd("wiretap simulator configure", hint="Change LLM / STT / TTS")
    else:
        ui.next_cmd("wiretap simulator configure", hint="Set up simulator")


__all__ = [
    "PLATFORM_API_KEYS",
    "configure_caller_interactive",
    "ensure_caller_configured",
    "ensure_env_key",
    "ensure_platform_key",
    "is_interactive",
    "pick_simulator_sections",
    "print_simulator_status",
    "print_status",
    "require_interactive",
]
