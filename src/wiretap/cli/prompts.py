"""Interactive CLI helpers — TTY-aware secret / caller setup.

Reuse onboard services; never echo secret values.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer
from rich import print

from wiretap.cli import style as ui
from wiretap.models import TransportKind
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

# Distribution packages installed by the optional ``pstn`` extra.
PSTN_PACKAGES = ("twilio", "pyVoIP")

# The run-time question is "web or phone", not a transport-kind quiz.
_PHONE_WORDS = {"phone", "pstn", "call", "dial"}
_WEB_WORDS = {"web", "online", "webrtc"}


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


def ensure_pstn_configured(
    *,
    cwd: Path | None = None,
    from_number: str | None = None,
) -> str:
    """Twilio credentials + caller number for a ``transport: pstn`` suite.

    Resolution order: explicit flag, TWILIO_FROM_NUMBER, previously saved choice,
    then an interactive pick from the account's own numbers.
    """
    from wiretap.services.twilio_pstn import (
        ACCOUNT_SID_ENV,
        AUTH_TOKEN_ENV,
        list_phone_numbers,
        resolve_from_number,
        save_from_number,
    )

    ensure_env_key(ACCOUNT_SID_ENV, label="Twilio Account SID", cwd=cwd)
    ensure_env_key(AUTH_TOKEN_ENV, label="Twilio auth token", cwd=cwd)

    chosen = (from_number or "").strip() or resolve_from_number(cwd)
    if not chosen:
        chosen = _pick_twilio_number(list_phone_numbers)
    try:
        saved = save_from_number(chosen, cwd)
    except ValueError as exc:
        ui.err(str(exc))
        raise typer.Exit(1) from exc
    ui.ok(f"Dialing from [bold]{saved}[/bold]")
    return saved


def _pick_twilio_number(fetch: Callable[..., list[dict[str, str]]]) -> str:
    """Show a page of numbers; large accounts search instead of scrolling."""
    from wiretap.services.twilio_pstn import NUMBER_PAGE_SIZE

    if not is_interactive():
        ui.err("No Twilio caller number selected.")
        ui.muted("Pass --from-number +1…, or set TWILIO_FROM_NUMBER in .env.")
        raise typer.Exit(1)

    contains: str | None = None
    while True:
        with ui.spinner("Loading Twilio phone numbers…"):
            try:
                numbers = fetch(limit=NUMBER_PAGE_SIZE, contains=contains)
            except RuntimeError as exc:
                ui.err(str(exc))
                raise typer.Exit(1) from exc

        if not numbers:
            if contains:
                ui.warn(f"No numbers matching {contains!r}.")
                contains = None
                continue
            ui.err("No phone numbers on this Twilio account.")
            ui.muted("Buy one in the Twilio console, then re-run.")
            raise typer.Exit(1)

        ui.info("Pick the number the test agent should call from")
        for index, entry in enumerate(numbers, 1):
            label = entry.get("friendly_name") or "—"
            print(
                f"  [bold {ui.ACCENT}]{index}[/bold {ui.ACCENT}]. "
                f"{entry['phone_number']}  [{ui.MUTED}]{label}[/{ui.MUTED}]"
            )
        if len(numbers) >= NUMBER_PAGE_SIZE:
            ui.muted(
                f"Showing {NUMBER_PAGE_SIZE} of your numbers — "
                "type part of a number to search."
            )

        raw = typer.prompt("Caller number (index, +E.164, or search)", default="1").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(numbers):
            return numbers[int(raw) - 1]["phone_number"]
        if raw.startswith("+"):
            return raw
        contains = raw


def require_pstn_extra() -> None:
    """Stop before any prompting when the optional phone dependencies are absent.

    Discovering this mid-dial wastes the setup the user just walked through.
    """
    from importlib.util import find_spec

    missing = [name for name in PSTN_PACKAGES if find_spec(name) is None]
    if not missing:
        return
    ui.err(f"Phone testing needs the pstn extra — {', '.join(missing)} not installed.")
    ui.muted("Install it with: uv sync --extra pstn")
    raise typer.Exit(1)


def choose_transport(suite: Any, *, transport: str | None = None) -> str:
    """Decide how this run reaches the agent, returning a transport kind.

    Phone is a per-run choice rather than a suite property, so the suite's own
    transport is only the default. Non-interactive runs keep that default so
    CI never blocks on a prompt.
    """
    current = suite.agent.transport.value
    if transport is not None and str(transport).strip():
        return _resolve_transport(str(transport), current=current)
    if not is_interactive():
        return current

    ui.info("Reach the agent over the web, or place a real phone call")
    choice = _pick("Transport", ["web", "phone"], default=_transport_word(current))
    return _resolve_transport(choice, current=current)


def _transport_word(kind: str) -> str:
    return "phone" if kind == "pstn" else "web"


def _resolve_transport(raw: str, *, current: str) -> str:
    """Map a user's word (or a literal transport kind) onto a TransportKind."""
    value = raw.strip().lower()
    if value in _PHONE_WORDS:
        return TransportKind.PSTN.value
    if value in _WEB_WORDS:
        # "web" means "however this suite normally connects", unless that is
        # itself the phone — then there is nothing to fall back to but webrtc.
        return TransportKind.WEBRTC.value if current == "pstn" else current
    try:
        return TransportKind(value).value
    except ValueError:
        ui.err(f"Unknown transport {raw!r}.")
        ui.muted("Use web or phone (or a transport kind: text, webrtc, sip, pstn).")
        raise typer.Exit(1) from None


def ensure_agent_number(
    suite: Any,
    *,
    phone: str | None = None,
    cwd: Path | None = None,
) -> str:
    """The agent's own phone number to dial for this run.

    Resolution order: explicit flag, the suite's declared target, the pick
    remembered for this agent, then a picker built from the platform's numbers.
    """
    from wiretap.services.agent_numbers import save_agent_number, saved_agent_number

    platform = suite.agent.platform
    agent_id = suite.agent.agent_id

    chosen = (phone or "").strip() or (suite.agent.phone_number or "").strip()
    if not chosen:
        chosen = (
            saved_agent_number(platform=platform, agent_id=agent_id, cwd=cwd) or ""
        )
    if not chosen:
        chosen = _pick_agent_number(
            platform=platform,
            agent_id=agent_id,
            token_env=suite.agent.token_env,
        )

    try:
        return save_agent_number(chosen, platform=platform, agent_id=agent_id, cwd=cwd)
    except ValueError as exc:
        ui.err(str(exc))
        raise typer.Exit(1) from exc


def _pick_agent_number(
    *,
    platform: str | None,
    agent_id: str | None,
    token_env: str | None,
) -> str:
    """Offer the numbers the platform routes to this agent, else ask outright."""
    if not is_interactive():
        ui.err("No phone number known for this agent.")
        ui.muted("Pass --phone +1…, or run wiretap simulate in a terminal to pick one.")
        raise typer.Exit(1)

    numbers = _discover_agent_numbers(
        platform=platform, agent_id=agent_id, token_env=token_env
    )
    if not numbers:
        ui.warn(f"Could not read phone numbers from {platform or 'the platform'}.")
        raw = typer.prompt("Agent phone number (+E.164)").strip()
        if not raw:
            ui.err("Aborted — a number is required to place the call")
            raise typer.Exit(1)
        return raw

    ui.info(f"Pick the number that reaches {agent_id or 'this agent'}")
    for index, entry in enumerate(numbers, 1):
        label = entry.label or "—"
        marker = "  ← this agent" if entry.bound else ""
        print(
            f"  [bold {ui.ACCENT}]{index}[/bold {ui.ACCENT}]. "
            f"{entry.number}  [{ui.MUTED}]{label}{marker}[/{ui.MUTED}]"
        )

    raw = typer.prompt("Agent number (index or +E.164)", default="1").strip()
    if raw.isdigit() and 1 <= int(raw) <= len(numbers):
        return numbers[int(raw) - 1].number
    return raw


def _discover_agent_numbers(
    *,
    platform: str | None,
    agent_id: str | None,
    token_env: str | None,
) -> list[Any]:
    import asyncio

    from wiretap.services.agent_numbers import (
        DISCOVERABLE_PLATFORMS,
        discover_agent_numbers,
    )

    name = (platform or "").lower().strip()
    if name not in DISCOVERABLE_PLATFORMS:
        return []
    api_key = _platform_api_key(platform=name, token_env=token_env)
    if not api_key:
        return []
    with ui.spinner(f"Loading {name} phone numbers…"):
        return asyncio.run(
            discover_agent_numbers(
                platform=name, agent_id=agent_id, api_key=api_key
            )
        )


def _platform_api_key(*, platform: str, token_env: str | None) -> str:
    """The platform key already in the secret store, or '' when unavailable."""
    from wiretap.providers.env import require_env

    env_name = (token_env or "").strip() or PLATFORM_API_KEYS.get(platform, "")
    if not env_name:
        return ""
    try:
        return require_env(env_name)
    except RuntimeError:
        return ""


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


def _phone_rows(cwd: Path | None = None) -> list[tuple[str, Any]]:
    """Whether `simulate --transport phone` could place a call right now."""
    from importlib.util import find_spec

    from rich.text import Text

    from wiretap.services.secrets import key_status
    from wiretap.services.twilio_pstn import (
        ACCOUNT_SID_ENV,
        AUTH_TOKEN_ENV,
        resolve_from_number,
    )

    keys = key_status(cwd)
    credentials = bool(keys.get(ACCOUNT_SID_ENV) and keys.get(AUTH_TOKEN_ENV))
    extra = all(find_spec(name) is not None for name in PSTN_PACKAGES)
    number = resolve_from_number(cwd) or ""

    if credentials and extra and number:
        state = Text("ready", style=f"bold {ui.OK}")
    else:
        missing = []
        if not extra:
            missing.append("uv sync --extra pstn")
        if not credentials:
            missing.append("Twilio keys")
        if not number:
            missing.append("caller number")
        state = Text("not configured", style=f"bold {ui.WARN}")
        state.append(f"  ({' · '.join(missing)})", style=ui.MUTED)

    rows: list[tuple[str, Any]] = [("Phone", state)]
    if number:
        rows.append(("Caller number", Text(number, style=ui.ACCENT)))
    return rows


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
    rows.extend(_phone_rows(cwd))
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
    "PSTN_PACKAGES",
    "choose_transport",
    "configure_caller_interactive",
    "ensure_agent_number",
    "ensure_caller_configured",
    "ensure_env_key",
    "ensure_platform_key",
    "ensure_pstn_configured",
    "is_interactive",
    "print_status",
    "require_interactive",
    "require_pstn_extra",
]
