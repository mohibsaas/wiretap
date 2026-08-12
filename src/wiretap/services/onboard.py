"""Onboarding orchestration: connect agent + generate categorized suites."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wiretap.suite import dump_suite
from wiretap.importers import (
    import_retell_agent,
    import_vapi_assistant,
)
from wiretap.importers.suite_builder import slug
from wiretap.importers.agent_graph import AgentGraph
from wiretap.models import SuiteConfig
from wiretap.paths import ensure_layout, graphs_dir, suite_path, wiretap_root
from wiretap.providers.catalog import (
    env_for_provider,
    known_provider_ids,
    provider_catalog,
)
from wiretap.services.generator import generate_suite, list_categories, parse_categories
from wiretap.services.secrets import key_status, upsert_secrets
from wiretap.services.suites import list_suites


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


def onboard_status(cwd: Path | None = None) -> dict[str, Any]:
    keys = key_status(cwd)
    suites = list_suites(cwd)
    state = load_onboard_state(cwd)
    llm = (state.get("llm_provider") or "openai").lower()
    if llm == "pyai":
        # Legacy onboard.json mistake — pyai is speech-only
        llm = "openai"
    stt = (state.get("stt") or "pyai").lower()
    tts = (state.get("tts") or "pyai").lower()
    catalog = provider_catalog()
    default_model = _default_model_for(llm, catalog)
    has_llm = _has_provider_key(keys, llm)
    speech_ok = _has_provider_key(keys, stt) and _has_provider_key(keys, tts)
    has_platform = bool(
        keys.get("RETELL_API_KEY")
        or keys.get("VAPI_API_KEY")
        or state.get("platform") == "custom"
    )
    return {
        "completed": bool(state.get("completed")),
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
        "caller": {
            "llm_provider": llm,
            "simulator_model": state.get("simulator_model") or default_model,
            "judge_model": state.get("judge_model") or default_model,
            "stt": stt,
            "tts": tts,
            "voice": state.get("voice") or "alloy",
        },
        "providers": catalog,
        "categories_catalog": list_categories(),
        "needs_onboarding": not bool(state.get("completed")) and len(suites) == 0,
    }


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



async def connect_agent(
    *,
    platform: str,
    agent_id: str | None = None,
    api_key: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Connect THEIR live agent. Caller LLM/STT/TTS is configured via configure_caller."""
    plat = platform.lower().strip()
    if plat not in {"retell", "vapi", "custom"}:
        raise ValueError("platform must be retell, vapi, or custom (phone/Bland live dial deferred)")

    keys = key_status(cwd)
    state = load_onboard_state(cwd)
    if not state.get("caller_configured"):
        # Allow resume if any common LLM key already exists
        if not (
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

    if plat == "retell" and not keys.get("RETELL_API_KEY"):
        raise ValueError("RETELL_API_KEY required")
    if plat == "vapi" and not keys.get("VAPI_API_KEY"):
        raise ValueError("VAPI_API_KEY required")

    suite: SuiteConfig | None = None
    graph: AgentGraph | None = None
    name = plat

    if plat == "custom":
        if not agent_id:
            agent_id = "custom"
        # Connect only stores state; generate writes the suite
        agent_name = agent_id
    else:
        if not agent_id:
            raise ValueError(f"{plat} requires agent_id")
        if plat == "retell":
            suite, graph = await import_retell_agent(agent_id)
            name = "retell"
        elif plat == "vapi":
            suite, graph = await import_vapi_assistant(agent_id)
            name = "vapi"
        else:
            raise ValueError(f"unsupported platform: {plat}")
        agent_name = suite.personas[0].identity if suite.personas else agent_id
        # Persist imported baseline suite + graph
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
            "suite_name": name if plat != "custom" else None,
            "connected": True,
        }
    )
    save_onboard_state(state, cwd)
    return {
        "platform": plat,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "suite_name": state.get("suite_name"),
        "imported": plat != "custom",
    }


def generate_onboard_suite(
    *,
    purpose: str = "",
    categories: list[str],
    tests_per_category: int = 5,
    suite_name: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    state = load_onboard_state(cwd)
    plat = (state.get("platform") or "custom").lower()
    agent_id = state.get("agent_id")
    agent_name = state.get("agent_name") or agent_id or "agent"
    name = suite_name or state.get("suite_name") or slug(f"{plat}_{agent_id or 'agent'}")

    # If we already imported a suite, reuse its agent target
    agent_kwargs: dict[str, Any] = {}
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
    suite = generate_suite(
        platform=str(agent_kwargs["platform"]),
        agent_id=agent_kwargs.get("agent_id"),
        agent_name=str(agent_name),
        purpose=purpose,
        categories=cats,
        tests_per_category=tests_per_category,
        transport=str(agent_kwargs.get("transport") or "webrtc"),
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
        key = f"{s.get('platform')}:{s.get('name')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": s["name"],
                "suite": s["name"],
                "platform": s.get("platform"),
                "transport": s.get("transport"),
                "scenario_count": s.get("scenario_count"),
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
                    "suite": state.get("suite_name"),
                    "platform": state.get("platform"),
                    "name": state.get("agent_name"),
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
