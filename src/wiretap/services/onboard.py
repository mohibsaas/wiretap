"""Onboarding orchestration: connect agent + generate categorized suites."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from wiretap.importers import (
    import_bolna_agent,
    import_elevenlabs_agent,
    import_retell_agent,
    import_synthflow_agent,
    import_vapi_assistant,
    suite_for_livekit_agent,
)
from wiretap.importers.agent_graph import AgentGraph
from wiretap.importers.suite_builder import slug
from wiretap.models import SuiteConfig
from wiretap.paths import ensure_layout, graphs_dir, suite_path, wiretap_root
from wiretap.providers.catalog import (
    env_for_provider,
    known_provider_ids,
    provider_catalog,
)
from wiretap.services.agent_brief import brief_for_suite
from wiretap.services.generator import generate_suite, list_categories, parse_categories
from wiretap.services.secrets import key_status, upsert_secrets
from wiretap.services.suites import get_suite, list_suites
from wiretap.suite import dump_suite


def onboard_state_path(cwd: Path | None = None) -> Path:
    return wiretap_root(cwd) / "onboard.json"


def load_onboard_state(cwd: Path | None = None) -> dict[str, Any]:
    path = onboard_state_path(cwd)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_onboard_state(data: dict[str, Any], cwd: Path | None = None) -> None:
    ensure_layout(cwd)
    # Never persist secrets in onboard.json
    clean = {k: v for k, v in data.items() if "key" not in k.lower() and "secret" not in k.lower()}
    onboard_state_path(cwd).write_text(json.dumps(clean, indent=2), encoding="utf-8")


def _has_provider_key(keys: dict[str, bool], provider_id: str) -> bool:
    return bool(keys.get(env_for_provider(provider_id)))


def _default_model_for(llm: str, catalog: dict[str, Any]) -> str:
    return next(
        (p["default_model"] for p in catalog["llm"] if p["id"] == llm),
        "gpt-4o-mini",
    )


# Keep status fast when the full LiteLLM catalog is not needed.
_DEFAULT_MODELS_FALLBACK: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
    "gemini": "gemini/gemini-2.0-flash",
    "groq": "groq/llama-3.3-70b-versatile",
    "mistral": "mistral/mistral-small-latest",
}


def onboard_status(
    cwd: Path | None = None,
    *,
    include_providers: bool = True,
) -> dict[str, Any]:
    keys = key_status(cwd)
    suites = list_suites(cwd)
    state = load_onboard_state(cwd)
    configured = bool(state.get("caller_configured"))
    # Defaults used only for capability probes / form seeds — not shown as
    # "configured" values until caller_configured is true.
    llm = (state.get("llm_provider") or "openai").lower()
    if llm == "pyai":
        # Legacy onboard.json mistake — pyai is speech-only
        llm = "openai"
    stt = (state.get("stt") or "pyai").lower()
    tts = (state.get("tts") or "pyai").lower()
    default_model = _DEFAULT_MODELS_FALLBACK.get(llm) or "gpt-4o-mini"
    if include_providers:
        catalog = provider_catalog()
        default_model = _default_model_for(llm, catalog)
    else:
        catalog = None
    has_llm = _has_provider_key(keys, llm)
    speech_ok = _has_provider_key(keys, stt) and _has_provider_key(keys, tts)
    has_platform = bool(
        keys.get("RETELL_API_KEY")
        or keys.get("VAPI_API_KEY")
        or keys.get("ELEVENLABS_API_KEY")
        or keys.get("LIVEKIT_API_KEY")
        or keys.get("SYNTHFLOW_API_KEY")
        or keys.get("BOLNA_API_KEY")
        or keys.get("BLAND_API_KEY")
        or state.get("platform") == "custom"
    )
    if configured:
        caller = {
            "llm_provider": llm,
            "simulator_model": state.get("simulator_model") or default_model,
            "judge_model": state.get("judge_model") or default_model,
            "stt": stt,
            "tts": tts,
            "voice": state.get("voice") or "alloy",
        }
    else:
        caller = {
            "llm_provider": None,
            "simulator_model": None,
            "judge_model": None,
            "stt": None,
            "tts": None,
            "voice": None,
        }
    out: dict[str, Any] = {
        "completed": bool(state.get("completed")),
        "caller_configured": configured,
        "has_llm_key": has_llm,
        "has_speech_key": speech_ok,
        "has_platform_key": has_platform,
        "platform": state.get("platform"),
        "agent_id": state.get("agent_id"),
        "agent_name": state.get("agent_name"),
        "purpose": state.get("purpose") or "",
        "suite_name": state.get("suite_name"),
        "categories": state.get("categories") or [],
        "suite_count": len(suites),
        "keys": keys,
        "caller": caller,
        "categories_catalog": list_categories(),
        "needs_onboarding": not bool(state.get("completed")) and len(suites) == 0,
    }
    if include_providers:
        out["providers"] = catalog
    return out


def configure_caller(
    *,
    llm_provider: str = "openai",
    llm_api_key: str | None = None,
    simulator_model: str = "gpt-4o-mini",
    judge_model: str = "gpt-4o-mini",
    stt: str = "pyai",
    tts: str = "pyai",
    voice: str = "alloy",
    speech_api_key: str | None = None,
    stt_api_key: str | None = None,
    tts_api_key: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Configure OUR test agent (LLM + STT/TTS). Secrets → .env only."""
    provider = (llm_provider or "openai").lower().strip()
    if provider == "pyai":
        raise ValueError("pyai is STT/TTS only — pick a LiteLLM provider for the test agent LLM")
    stt_name = (stt or "pyai").lower().strip()
    tts_name = (tts or "pyai").lower().strip()
    if stt_name == "whisper":
        stt_name = "openai"

    if provider not in known_provider_ids("llm"):
        raise ValueError(f"Unknown LLM provider: {provider!r}")
    if stt_name not in known_provider_ids("stt"):
        raise ValueError(f"Unknown STT provider: {stt_name!r}")
    if tts_name not in known_provider_ids("tts"):
        raise ValueError(f"Unknown TTS provider: {tts_name!r}")

    stt_key = (stt_api_key or speech_api_key or "").strip()
    tts_key = (tts_api_key or speech_api_key or "").strip()
    to_save: dict[str, str] = {}
    if llm_api_key and llm_api_key.strip():
        to_save[env_for_provider(provider)] = llm_api_key.strip()
    if stt_key:
        env = env_for_provider(stt_name)
        if env not in to_save:
            to_save[env] = stt_key
    if tts_key:
        env = env_for_provider(tts_name)
        if env not in to_save:
            to_save[env] = tts_key
    if to_save:
        upsert_secrets(to_save, cwd)

    keys = key_status(cwd)
    if not _has_provider_key(keys, provider):
        raise ValueError(f"{env_for_provider(provider)} required for LLM provider {provider!r}")
    if not _has_provider_key(keys, stt_name):
        raise ValueError(f"{env_for_provider(stt_name)} required for STT provider {stt_name!r}")
    if not _has_provider_key(keys, tts_name):
        raise ValueError(f"{env_for_provider(tts_name)} required for TTS provider {tts_name!r}")

    default_model = _default_model_for(provider, provider_catalog())
    state = load_onboard_state(cwd)
    state.update(
        {
            "llm_provider": provider,
            "simulator_model": (simulator_model or "").strip() or default_model,
            "judge_model": (judge_model or "").strip() or default_model,
            "stt": stt_name,
            "tts": tts_name,
            "voice": (voice or "alloy").strip() or "alloy",
            "caller_configured": True,
        }
    )
    save_onboard_state(state, cwd)
    return {"caller": onboard_status(cwd)["caller"], "keys": key_status(cwd)}



_LIVE_IMPORT_PLATFORMS = frozenset(
    {"retell", "vapi", "elevenlabs", "livekit", "synthflow", "bolna", "custom"}
)
# Import-only / deferred dial — still allowed for suite drafting
_DEFERRED_LIVE = frozenset({"bolna", "bland"})


async def connect_agent(
    *,
    platform: str,
    agent_id: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
    room_url: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Connect THEIR live agent. Caller LLM/STT/TTS is configured via configure_caller."""
    plat = platform.lower().strip()
    if plat not in _LIVE_IMPORT_PLATFORMS:
        raise ValueError(
            "platform must be retell, vapi, elevenlabs, livekit, synthflow, bolna, or custom"
        )

    keys = key_status(cwd)
    state = load_onboard_state(cwd)
    if not state.get("caller_configured") and not (
        keys.get("PYAI_API_KEY")
        or keys.get("OPENAI_API_KEY")
        or keys.get("ANTHROPIC_API_KEY")
    ):
        raise ValueError("Configure the test agent (LLM + STT/TTS) first")

    if api_key:
        if plat == "custom":
            raise ValueError("custom platform does not use a platform API key here")
        upsert_secrets({f"{plat.upper()}_API_KEY": api_key}, cwd)
        keys = key_status(cwd)
    if api_secret and plat == "livekit":
        upsert_secrets({"LIVEKIT_API_SECRET": api_secret}, cwd)
        keys = key_status(cwd)

    _require_platform_key(plat, keys)

    suite: SuiteConfig | None = None
    graph: AgentGraph | None = None
    # Unique per agent so adding another agent does not overwrite.
    name = slug(f"{plat}_{agent_id or 'agent'}")[:48] or plat

    if plat == "custom":
        if not agent_id:
            agent_id = "custom"
            name = slug("custom") or "custom"
        agent_name = agent_id
    else:
        if not agent_id:
            raise ValueError(f"{plat} requires agent_id")
        if plat == "retell":
            suite, graph = await import_retell_agent(agent_id)
        elif plat == "vapi":
            suite, graph = await import_vapi_assistant(agent_id)
        elif plat == "elevenlabs":
            suite, graph = await import_elevenlabs_agent(agent_id)
        elif plat == "synthflow":
            suite, graph = await import_synthflow_agent(agent_id)
        elif plat == "bolna":
            suite, graph = await import_bolna_agent(agent_id)
        elif plat == "livekit":
            url = (room_url or "").strip()
            if not url:
                raise ValueError("livekit requires room_url (wss://…)")
            suite, graph = suite_for_livekit_agent(
                room_name=agent_id, room_url=url
            )
        else:
            raise ValueError(f"unsupported platform: {plat}")
        agent_name = suite.personas[0].identity if suite.personas else agent_id
        ensure_layout(cwd)
        path = suite_path(name, cwd)
        dump_suite(suite, path)
        if graph:
            ir_path = graphs_dir(cwd) / f"{name}.graph.json"
            ir_path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")

    state.update(
        {
            "platform": plat,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "suite_name": name,
            "connected": True,
            "room_url": (room_url or "").strip() or None,
        }
    )
    save_onboard_state(state, cwd)
    return {
        "platform": plat,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "suite_name": state.get("suite_name"),
        "imported": plat != "custom",
        "live_deferred": plat in _DEFERRED_LIVE,
    }


def _require_platform_key(plat: str, keys: dict[str, bool]) -> None:
    if plat == "livekit":
        if keys.get("LIVEKIT_TOKEN"):
            return
        if not keys.get("LIVEKIT_API_KEY"):
            raise ValueError("LIVEKIT_API_KEY required (or set LIVEKIT_TOKEN)")
        if not keys.get("LIVEKIT_API_SECRET"):
            raise ValueError("LIVEKIT_API_SECRET required (or set LIVEKIT_TOKEN)")
        return
    required = {
        "retell": "RETELL_API_KEY",
        "vapi": "VAPI_API_KEY",
        "elevenlabs": "ELEVENLABS_API_KEY",
        "synthflow": "SYNTHFLOW_API_KEY",
        "bolna": "BOLNA_API_KEY",
    }.get(plat)
    if required and not keys.get(required):
        raise ValueError(f"{required} required")


def generate_onboard_suite(
    *,
    purpose: str = "",
    categories: list[str],
    tests_per_category: int = 5,
    suite_name: str | None = None,
    cwd: Path | None = None,
    on_progress=None,
) -> dict[str, Any]:
    state = load_onboard_state(cwd)
    plat = (state.get("platform") or "custom").lower()
    agent_id = state.get("agent_id")
    agent_name = state.get("agent_name") or agent_id or "agent"
    name = suite_name or state.get("suite_name") or slug(f"{plat}_{agent_id or 'agent'}")

    # If we already imported a suite, reuse its agent target
    agent_kwargs: dict[str, Any] = {}
    existing: SuiteConfig | None = None
    existing_path = suite_path(name, cwd) if state.get("suite_name") else None
    if existing_path and existing_path.is_file():
        from wiretap.suite import load_suite

        existing = load_suite(existing_path)
        agent_kwargs = {
            "platform": existing.agent.platform or plat,
            "agent_id": existing.agent.agent_id or agent_id,
            "transport": existing.agent.transport.value,
        }
    else:
        agent_kwargs = {
            "platform": plat,
            "agent_id": agent_id,
            "transport": "text" if plat == "custom" else "webrtc",
        }

    cats = parse_categories(categories)
    model = str(state.get("simulator_model") or "gpt-4o-mini")
    brief = brief_for_suite(
        name,
        suite=existing,
        purpose=purpose,
        agent_name=str(agent_name),
        cwd=cwd,
    )
    suite = generate_suite(
        platform=str(agent_kwargs["platform"]),
        agent_id=agent_kwargs.get("agent_id"),
        agent_name=str(agent_name),
        purpose=purpose,
        categories=cats,
        tests_per_category=tests_per_category,
        transport=str(agent_kwargs.get("transport") or "webrtc"),
        model=model,
        brief=brief,
        on_progress=on_progress,
    )
    # Apply OUR test agent stack from onboarding
    suite.models.simulator = str(state.get("simulator_model") or suite.models.simulator)
    suite.models.judge = str(state.get("judge_model") or suite.models.judge)
    suite.speech.stt = str(state.get("stt") or suite.speech.stt)
    suite.speech.tts = str(state.get("tts") or suite.speech.tts)
    suite.speech.voice = state.get("voice") or suite.speech.voice

    # Preserve token_env from import platforms
    if existing_path and existing_path.is_file():
        from wiretap.suite import load_suite

        existing = load_suite(existing_path)
        suite.agent.token_env = existing.agent.token_env
        suite.agent.room_url = existing.agent.room_url

    ensure_layout(cwd)
    path = suite_path(name, cwd)
    dump_suite(suite, path)
    state.update(
        {
            "purpose": purpose,
            "categories": cats,
            "tests_per_category": tests_per_category,
            "suite_name": name,
            "completed": True,
        }
    )
    save_onboard_state(state, cwd)
    return {
        "suite_name": name,
        "path": str(path),
        "scenario_count": len(suite.scenarios),
        "categories": cats,
    }


def list_agents(cwd: Path | None = None) -> list[dict[str, Any]]:
    """Agents as seen through local suites (no remote directory yet)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s in list_suites(cwd):
        if s.get("error"):
            continue
        try:
            suite = get_suite(s["name"], cwd)
        except (OSError, ValueError, TypeError, ValidationError):
            continue
        agent_id = suite.agent.agent_id
        key = f"{suite.agent.platform}:{agent_id or s['name']}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": agent_id or s["name"],
                "agent_id": agent_id,
                "suite": s["name"],
                "platform": suite.agent.platform,
                "transport": suite.agent.transport.value,
                "name": agent_id or s["name"],
                "scenario_count": s.get("scenario_count"),
                "token_env": suite.agent.token_env,
            }
        )
    state = load_onboard_state(cwd)
    if state.get("agent_id") and state.get("platform"):
        oid = f"onboard:{state['platform']}:{state['agent_id']}"
        if oid not in seen:
            out.insert(
                0,
                {
                    "id": state.get("agent_id"),
                    "agent_id": state.get("agent_id"),
                    "suite": state.get("suite_name"),
                    "platform": state.get("platform"),
                    "name": state.get("agent_name") or state.get("agent_id"),
                    "connected": True,
                },
            )
    return out


__all__ = [
    "configure_caller",
    "connect_agent",
    "generate_onboard_suite",
    "list_agents",
    "load_onboard_state",
    "onboard_status",
    "save_onboard_state",
]
