"""Fetch the live agent prompt, preview a combined draft, write it back.

The advisor never sees the full prompt. Apply always GETs the live prompt at
click time, appends the selected suggested_text blocks, and PATCHes once after
the user confirms the exact draft. A hash check aborts if the live prompt moved
between preview and apply.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx

from wiretap.models import RunAdvice, SuiteConfig
from wiretap.providers.catalog import env_for_provider
from wiretap.providers.env import require_env
from wiretap.services.agent_brief import sanitize_text

WRITABLE = ("retell", "vapi", "elevenlabs")
TEXT_CAP = 600
_TIMEOUT = 30.0
_SENTENCE = re.compile(r"(?<=[.!?])(?:\s+|$)")
_SIMILAR_RATIO = 0.88


class PromptApplyError(Exception):
    """User-facing apply failure. ``status`` maps to the HTTP code."""

    def __init__(self, message: str, *, status: int = 400, code: str = "apply_error"):
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass
class LivePrompt:
    platform: str
    agent_id: str
    current: str
    extra: dict[str, Any]


def prompt_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def compose_draft(current: str, additions: list[str]) -> str:
    """Append selected wording after the live prompt. Never invent a merge."""
    body = (current or "").rstrip()
    bits = [a.strip() for a in additions if a and a.strip()]
    if not bits:
        return body
    extra = "\n\n".join(bits)
    return f"{body}\n\n{extra}" if body else extra


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def coverage_reason(current: str, addition: str, queued: list[str]) -> str | None:
    """Why this block should not be written, or None if it is new."""
    needle = _norm(addition)
    if not needle:
        return "already_in_prompt"
    for prior in queued:
        if needle == prior or needle in prior:
            return "already_in_selection"
    if _covered_by(current, addition):
        return "already_in_prompt"
    return None


def _covered_by(current: str, addition: str) -> bool:
    haystack = _norm(current)
    needle = _norm(addition)
    if not needle:
        return True
    if needle in haystack:
        return True
    sentences = [
        _norm(part)
        for part in _SENTENCE.split(addition)
        if len(_norm(part)) >= 20
    ]
    if sentences and all(sent in haystack for sent in sentences):
        return True
    for para in (current or "").splitlines():
        blob = _norm(para)
        if (
            len(needle) >= 32
            and len(blob) >= 32
            and SequenceMatcher(None, needle, blob).ratio() >= _SIMILAR_RATIO
        ):
            return True
    n_tokens = needle.split()
    h_tokens = haystack.split()
    window = len(n_tokens)
    if 8 <= window <= 80 and len(h_tokens) >= window:
        step = max(1, window // 4)
        for i in range(0, len(h_tokens) - window + 1, step):
            chunk = " ".join(h_tokens[i : i + window])
            if SequenceMatcher(None, needle, chunk).ratio() >= 0.9:
                return True
    return False


def filter_new_additions(
    current: str, items: list[tuple[str, str]]
) -> tuple[list[tuple[str, str]], list[dict[str, str]]]:
    """Drop blocks the live prompt (or an earlier pick) already covers."""
    new: list[tuple[str, str]] = []
    skipped: list[dict[str, str]] = []
    queued: list[str] = []
    for fid, text in items:
        reason = coverage_reason(current, text, queued)
        if reason:
            skipped.append({"id": fid, "text": text, "reason": reason})
            continue
        new.append((fid, text))
        queued.append(_norm(text))
    return new, skipped


def prompt_diff(current: str, draft: str) -> list[dict[str, str]]:
    """Line-level git-style hunks of current → draft."""
    old = current or ""
    new = draft or ""
    if new.startswith(old):
        hunks = []
        if old:
            hunks.append({"op": "equal", "text": old})
        rest = new[len(old) :]
        if rest:
            hunks.append({"op": "insert", "text": rest})
        return [h for h in hunks if h["text"]]
    stripped = old.rstrip()
    if stripped and new.startswith(stripped):
        hunks = [{"op": "equal", "text": stripped}]
        trail = old[len(stripped) :]
        if trail:
            hunks.append({"op": "delete", "text": trail})
        rest = new[len(stripped) :]
        if rest:
            hunks.append({"op": "insert", "text": rest})
        return [h for h in hunks if h["text"]]
    prev = stripped.splitlines(keepends=True)
    nxt = new.splitlines(keepends=True)
    hunks = []
    matcher = SequenceMatcher(a=prev, b=nxt, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            hunks.append({"op": "equal", "text": "".join(prev[i1:i2])})
        elif tag == "insert":
            hunks.append({"op": "insert", "text": "".join(nxt[j1:j2])})
        elif tag == "delete":
            hunks.append({"op": "delete", "text": "".join(prev[i1:i2])})
        else:
            hunks.append({"op": "delete", "text": "".join(prev[i1:i2])})
            hunks.append({"op": "insert", "text": "".join(nxt[j1:j2])})
    return [h for h in hunks if h["text"]]


def select_additions(
    advice: RunAdvice, finding_ids: list[str]
) -> list[tuple[str, str]]:
    """Return (id, sanitized suggested_text) for prompt-target findings, in request order."""
    by_id = {f.id: f for f in advice.findings if f.id}
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_id in finding_ids:
        fid = str(raw_id or "").strip()
        if not fid or fid in seen:
            continue
        finding = by_id.get(fid)
        if finding is None or finding.target != "agent_prompt":
            continue
        text = sanitize_text(finding.suggested_text, cap=TEXT_CAP)
        if not text:
            continue
        seen.add(fid)
        out.append((fid, text))
    return out


def platform_writable(platform: str | None) -> bool:
    return (platform or "").strip().lower() in WRITABLE


async def fetch_live_prompt(suite: SuiteConfig) -> LivePrompt:
    platform = (suite.agent.platform or "").strip().lower()
    agent_id = (suite.agent.agent_id or "").strip()
    if not platform_writable(platform):
        raise PromptApplyError(
            f"This platform has no prompt write API ({platform or 'unknown'}).",
            code="unsupported_platform",
        )
    if not agent_id:
        raise PromptApplyError("Suite has no agent_id to update.", code="missing_agent")
    key = _api_key(suite, platform)
    if platform == "retell":
        return await _retell_get(agent_id, key)
    if platform == "vapi":
        return await _vapi_get(agent_id, key)
    return await _eleven_get(agent_id, key)


async def write_live_prompt(suite: SuiteConfig, *, draft: str, live: LivePrompt) -> None:
    key = _api_key(suite, live.platform)
    if live.platform == "retell":
        await _retell_patch(live, draft, key)
    elif live.platform == "vapi":
        await _vapi_patch(live, draft, key)
    else:
        await _eleven_patch(live, draft, key)


async def preview_prompt(
    suite: SuiteConfig,
    advice: RunAdvice,
    finding_ids: list[str],
) -> dict[str, Any]:
    additions = select_additions(advice, finding_ids)
    if not additions:
        raise PromptApplyError(
            "No prompt findings selected. Pick at least one prompt improvement.",
            code="no_findings",
        )
    live = await fetch_live_prompt(suite)
    new, skipped = filter_new_additions(live.current, additions)
    draft = compose_draft(live.current, [text for _, text in new])
    return {
        "platform": live.platform,
        "agent_id": live.agent_id,
        "current": live.current,
        "additions": [text for _, text in new],
        "skipped": skipped,
        "diff": prompt_diff(live.current, draft),
        "draft": draft,
        "current_hash": prompt_hash(live.current),
        "applied_finding_ids": [fid for fid, _ in new],
        "writable": True,
        "unchanged": not new,
    }


async def apply_prompt(
    suite: SuiteConfig,
    advice: RunAdvice,
    finding_ids: list[str],
    *,
    current_hash: str,
    cwd: Path | None = None,
    suite_id: str = "",
) -> dict[str, Any]:
    additions = select_additions(advice, finding_ids)
    if not additions:
        raise PromptApplyError(
            "No prompt findings selected. Pick at least one prompt improvement.",
            code="no_findings",
        )
    live = await fetch_live_prompt(suite)
    if prompt_hash(live.current) != (current_hash or "").strip():
        raise PromptApplyError(
            "The live prompt changed since preview. Preview again.",
            status=409,
            code="prompt_changed",
        )
    new, _skipped = filter_new_additions(live.current, additions)
    if not new:
        raise PromptApplyError(
            "The live prompt already contains this wording. Nothing to write.",
            code="already_present",
        )
    draft = compose_draft(live.current, [text for _, text in new])
    await write_live_prompt(suite, draft=draft, live=live)
    _refresh_local_graph(draft, suite_id=suite_id, cwd=cwd)
    return {
        "platform": live.platform,
        "agent_id": live.agent_id,
        "applied_finding_ids": [fid for fid, _ in new],
        "ok": True,
    }


def advice_from_run(run: dict[str, Any]) -> RunAdvice | None:
    raw = run.get("advice")
    if not isinstance(raw, dict):
        return None
    try:
        return RunAdvice.model_validate(raw)
    except Exception:  # noqa: BLE001
        return None


def _api_key(suite: SuiteConfig, platform: str) -> str:
    env_name = (suite.agent.token_env or "").strip() or env_for_provider(platform)
    try:
        return require_env(env_name)
    except RuntimeError as exc:
        raise PromptApplyError(str(exc), code="missing_key") from exc


def _refresh_local_graph(draft: str, *, suite_id: str, cwd: Path | None) -> None:
    """Best-effort: keep the imported snapshot from lying after a live write."""
    if not suite_id:
        return
    from wiretap.importers.agent_graph import NodeType
    from wiretap.paths import graphs_dir
    from wiretap.services.agent_brief import load_agent_graph

    graph = load_agent_graph(suite_id, cwd=cwd)
    if graph is None:
        return
    target = next((n for n in graph.nodes if n.id == graph.entry_node_id and n.prompt), None)
    if target is None:
        target = next(
            (n for n in graph.nodes if n.type is NodeType.CONVERSATION and n.prompt),
            None,
        )
    if target is None:
        return
    target.prompt = draft
    path = graphs_dir(cwd) / f"{suite_id}.graph.json"
    try:
        path.write_text(graph.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except OSError:
        return


# --- platform adapters -------------------------------------------------------


async def _retell_get(agent_id: str, key: str) -> LivePrompt:
    headers = {"Authorization": f"Bearer {key}"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        agent_resp = await client.get(
            f"https://api.retellai.com/get-agent/{agent_id}", headers=headers
        )
        _raise_platform(agent_resp, "Retell")
        agent = agent_resp.json()
        engine = agent.get("response_engine") or {}
        llm_id = ""
        if isinstance(engine, dict):
            llm_id = str(engine.get("llm_id") or engine.get("id") or "")
        if not llm_id:
            raise PromptApplyError(
                "Retell agent has no LLM id, so there is no prompt to update.",
                code="missing_llm",
            )
        llm_resp = await client.get(
            f"https://api.retellai.com/get-retell-llm/{llm_id}", headers=headers
        )
        _raise_platform(llm_resp, "Retell")
        llm = llm_resp.json()
    return LivePrompt(
        platform="retell",
        agent_id=agent_id,
        current=str(llm.get("general_prompt") or ""),
        extra={"llm_id": llm_id},
    )


async def _retell_patch(live: LivePrompt, draft: str, key: str) -> None:
    llm_id = str(live.extra.get("llm_id") or "")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.patch(
            f"https://api.retellai.com/update-retell-llm/{llm_id}",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"general_prompt": draft},
        )
        _raise_platform(resp, "Retell")


async def _vapi_get(agent_id: str, key: str) -> LivePrompt:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"https://api.vapi.ai/assistant/{agent_id}",
            headers={"Authorization": f"Bearer {key}"},
        )
        _raise_platform(resp, "Vapi")
        data = resp.json()
    model = data.get("model") if isinstance(data.get("model"), dict) else {}
    messages = list(model.get("messages") or [])
    parts = [
        str(m.get("content") or "")
        for m in messages
        if isinstance(m, dict) and m.get("role") == "system"
    ]
    return LivePrompt(
        platform="vapi",
        agent_id=agent_id,
        current="\n\n".join(p for p in parts if p),
        extra={"model": model, "messages": messages},
    )


async def _vapi_patch(live: LivePrompt, draft: str, key: str) -> None:
    model = dict(live.extra.get("model") or {})
    messages = list(live.extra.get("messages") or [])
    rest = [m for m in messages if not (isinstance(m, dict) and m.get("role") == "system")]
    model["messages"] = [{"role": "system", "content": draft}, *rest]
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.patch(
            f"https://api.vapi.ai/assistant/{live.agent_id}",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"model": model},
        )
        _raise_platform(resp, "Vapi")


async def _eleven_get(agent_id: str, key: str) -> LivePrompt:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"https://api.elevenlabs.io/v1/convai/agents/{agent_id}",
            headers={"xi-api-key": key},
        )
        _raise_platform(resp, "ElevenLabs")
        data = resp.json()
    cfg = data.get("conversation_config") or {}
    agent = cfg.get("agent") or {}
    prompt_obj = agent.get("prompt") or {}
    if isinstance(prompt_obj, dict):
        current = str(prompt_obj.get("prompt") or "")
    else:
        current = str(prompt_obj or "")
    return LivePrompt(
        platform="elevenlabs",
        agent_id=agent_id,
        current=current,
        extra={},
    )


async def _eleven_patch(live: LivePrompt, draft: str, key: str) -> None:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.patch(
            f"https://api.elevenlabs.io/v1/convai/agents/{live.agent_id}",
            headers={"xi-api-key": key, "Content-Type": "application/json"},
            json={"conversation_config": {"agent": {"prompt": {"prompt": draft}}}},
        )
        _raise_platform(resp, "ElevenLabs")


def _raise_platform(resp: httpx.Response, name: str) -> None:
    if resp.is_success:
        return
    # Never echo the body — it can contain the prompt or a leaked key.
    raise PromptApplyError(
        f"{name} returned HTTP {resp.status_code}. The live prompt was not changed.",
        status=502,
        code="platform_error",
    )


__all__ = [
    "WRITABLE",
    "LivePrompt",
    "PromptApplyError",
    "advice_from_run",
    "apply_prompt",
    "compose_draft",
    "coverage_reason",
    "fetch_live_prompt",
    "filter_new_additions",
    "platform_writable",
    "preview_prompt",
    "prompt_diff",
    "prompt_hash",
    "select_additions",
]
