"""Category-tagged suite generation via LLM (LiteLLM).

Categories are eval buckets (emotional, compliance, …). Scenario content is
generated with the configured simulator model — not static templates.
Catalog entries keep short few-shot examples to steer the model.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from wiretap.importers.suite_builder import slug
from wiretap.models import (
    AgentTarget,
    Beat,
    ModelSlots,
    Persona,
    RuleCheck,
    Scenario,
    SpeechConfig,
    SuiteConfig,
    TransportKind,
)
from wiretap.prompts.agent_brief import agent_brief_from_purpose_only
from wiretap.prompts.categories import (
    CATEGORY_CATALOG,
    DEFAULT_CATEGORIES,
    MAX_TESTS_PER_CATEGORY,
)
from wiretap.prompts.defaults import (
    DEFAULT_CALLER_OPENING,
    DEFAULT_GENERATED_RUBRIC,
    DEFAULT_PERSONA_PERSONALITY,
    DEFAULT_SUCCESS_CRITERIA,
    DO_NOT_REVEAL_TEST_BOT,
)
from wiretap.prompts.suite_generation import (
    SUITE_GENERATION_SYSTEM,
    suite_generation_context,
    suite_generation_retry_user_message,
    suite_generation_user_message,
)
from wiretap.providers.llm import complete

ProgressCallback = Callable[[dict[str, Any]], None]

def list_categories() -> list[dict[str, Any]]:
    out = []
    for key, meta in CATEGORY_CATALOG.items():
        out.append(
            {
                "id": key,
                "label": meta["label"],
                "description": meta["description"],
                "max_tests": MAX_TESTS_PER_CATEGORY,
            }
        )
    return out


def _unique_slug(value: str, seen: set[str], *, limit: int = 48) -> str:
    base = slug(value)[:limit] or "item"
    out = base
    n = 2
    while out in seen:
        out = f"{base}_{n}"
        n += 1
    seen.add(out)
    return out


def _persona_slug(identity: str) -> str:
    """Short id from identity, e.g. 'A frustrated customer who…' → frustrated_customer."""
    text = identity.strip()
    text = re.sub(r"^(a|an|the)\s+", "", text, flags=re.IGNORECASE)
    cut = re.split(
        r"\s+(?:who|that|worried|demanding|claiming|trying)\s+",
        text,
        maxsplit=1,
    )
    head = cut[0] if cut else text
    return slug(head)[:40] or "caller"


def parse_categories(raw: str | list[str] | None) -> list[str]:
    """Parse CLI/UI category lists; fall back to defaults."""
    if raw is None:
        return list(DEFAULT_CATEGORIES)
    if isinstance(raw, list):
        cats = [str(c).strip().lower() for c in raw if str(c).strip()]
    else:
        cats = [c.strip().lower() for c in str(raw).split(",") if c.strip()]
    if not cats:
        return list(DEFAULT_CATEGORIES)
    unknown = [c for c in cats if c not in CATEGORY_CATALOG]
    if unknown:
        raise ValueError(
            f"Unknown categor{'y' if len(unknown) == 1 else 'ies'}: {', '.join(unknown)}. "
            f"Choose from: {', '.join(CATEGORY_CATALOG)}"
        )
    return cats


def _extract_json_array(text: str) -> list[Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("LLM returned empty content for suite generation")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[")
        end = raw.rfind("]")
        if start < 0 or end <= start:
            raise ValueError(f"LLM did not return JSON array: {raw[:200]}")
        data = json.loads(raw[start : end + 1])
    if not isinstance(data, list):
        raise ValueError("LLM JSON must be an array of test cases")
    return data


def _normalize_test(item: Any, *, category: str, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"Test case {index} in {category} is not an object")
    name = str(item.get("name") or "").strip() or f"{category} scenario {index + 1}"
    identity = str(item.get("identity") or "").strip() or f"A caller for {name}"
    goal = str(item.get("goal") or "").strip() or f"Complete the call goal for {name}"
    say = str(item.get("say") or "").strip() or DEFAULT_CALLER_OPENING
    success = str(item.get("success") or "").strip() or DEFAULT_SUCCESS_CRITERIA
    excludes = item.get("excludes") or []
    if not isinstance(excludes, list):
        excludes = []
    excludes = [str(x).strip() for x in excludes if str(x).strip()]
    return {
        "name": name,
        "identity": identity,
        "goal": goal,
        "say": say,
        "success": success,
        "excludes": excludes,
    }


def llm_generate_category_tests(
    *,
    category: str,
    count: int,
    agent_name: str,
    purpose: str = "",
    model: str = "gpt-4o-mini",
    agent_brief: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Ask the LLM for ``count`` distinct test cases in one category."""
    meta = CATEGORY_CATALOG[category]
    n = max(1, min(MAX_TESTS_PER_CATEGORY, count))
    examples = meta.get("examples") or []
    brief = agent_brief or agent_brief_from_purpose_only(
        agent_name=agent_name,
        purpose=purpose,
    )
    context = suite_generation_context(
        agent_name=agent_name,
        purpose=purpose,
        category=category,
        category_label=str(meta["label"]),
        category_description=str(meta["description"]),
        count=n,
        few_shot_examples=list(examples),
        agent_brief=brief,
    )
    content = complete(
        model=model,
        messages=[
            {"role": "system", "content": SUITE_GENERATION_SYSTEM},
            {
                "role": "user",
                "content": suite_generation_user_message(n, context),
            },
        ],
        temperature=0.7,
        max_tokens=3500,
    )
    items = _extract_json_array(content)
    if len(items) < n:
        # Ask once more for the missing count rather than padding templates.
        need = n - len(items)
        extra = complete(
            model=model,
            messages=[
                {"role": "system", "content": SUITE_GENERATION_SYSTEM},
                {
                    "role": "user",
                    "content": suite_generation_retry_user_message(
                        need=need,
                        category=category,
                        agent_name=agent_name,
                        existing_names=[
                            str(i.get("name")) for i in items if isinstance(i, dict)
                        ],
                        context=context,
                    ),
                },
            ],
            temperature=0.8,
            max_tokens=2000,
        )
        items.extend(_extract_json_array(extra))
    out = [_normalize_test(item, category=category, index=i) for i, item in enumerate(items[:n])]
    if len(out) < n:
        raise ValueError(
            f"LLM returned only {len(out)}/{n} tests for category {category!r}"
        )
    return out


def generate_suite(
    *,
    platform: str,
    agent_id: str | None,
    agent_name: str,
    purpose: str = "",
    categories: list[str] | None = None,
    tests_per_category: int = 5,
    transport: str = "webrtc",
    model: str | None = None,
    agent_brief: dict[str, Any] | None = None,
    on_progress: ProgressCallback | None = None,
) -> SuiteConfig:
    """Build a SuiteConfig by LLM-generating scenarios for each category.

    ``on_progress`` receives dict events with ``kind`` in
    ``start | category_start | category_done | done`` plus ``done``/``total``.
    """
    cats = parse_categories(categories)
    n = max(1, min(MAX_TESTS_PER_CATEGORY, tests_per_category))
    model_name = (model or "gpt-4o-mini").strip() or "gpt-4o-mini"
    personas: list[Persona] = []
    scenarios: list[Scenario] = []
    purpose_bit = purpose.strip()
    seen_ids: set[str] = set()
    seen_personas: set[str] = set()
    total = len(cats) * n
    done = 0

    def _emit(kind: str, **extra: Any) -> None:
        if on_progress is None:
            return
        payload: dict[str, Any] = {"kind": kind, "done": done, "total": total}
        payload.update(extra)
        on_progress(payload)

    _emit("start", categories=list(cats))

    for cat in cats:
        _emit("category_start", category=cat, batch=n)
        tests = llm_generate_category_tests(
            category=cat,
            count=n,
            agent_name=agent_name or "the agent",
            purpose=purpose_bit,
            model=model_name,
            agent_brief=agent_brief,
        )
        for t in tests:
            pid = _unique_slug(_persona_slug(str(t["identity"])), seen_personas)
            personas.append(
                Persona(
                    id=pid,
                    name=str(t["name"]),
                    identity=t["identity"],
                    goal=t["goal"]
                    + (f" Context: {purpose_bit}" if purpose_bit else ""),
                    personality=DEFAULT_PERSONA_PERSONALITY,
                    constraints=[DO_NOT_REVEAL_TEST_BOT],
                )
            )
            success = t["success"]
            if purpose_bit:
                success = f"{success} Align with purpose: {purpose_bit}"
            scenarios.append(
                Scenario(
                    id=_unique_slug(str(t["name"]), seen_ids),
                    name=str(t["name"]),
                    persona_id=pid,
                    max_turns=10,
                    success_criteria=success,
                    rubric=DEFAULT_GENERATED_RUBRIC,
                    rules=RuleCheck(excludes=list(t.get("excludes") or [])),
                    beats=[Beat(at_turn=1, say=t["say"])],
                    category=cat,
                )
            )
        done += len(tests)
        _emit(
            "category_done",
            category=cat,
            batch=len(tests),
            titles=[str(t.get("name") or "").strip() or f"{cat} scenario" for t in tests],
        )

    _emit("done")

    plat = (platform or "custom").lower().strip()
    try:
        kind = TransportKind(transport)
    except ValueError:
        kind = TransportKind.TEXT if plat == "custom" else TransportKind.WEBRTC

    token_env = _token_env_for_platform(plat)
    if plat == "custom":
        kind = TransportKind.TEXT
        token_env = None

    return SuiteConfig(
        agent=AgentTarget(
            transport=kind,
            platform=None if plat == "custom" else plat,
            agent_id=agent_id,
            token_env=token_env,
        ),
        models=ModelSlots(simulator=model_name, judge=model_name),
        speech=SpeechConfig(),
        personas=personas,
        scenarios=scenarios,
    )


def _token_env_for_platform(plat: str) -> str | None:
    mapping = {
        "retell": "RETELL_API_KEY",
        "vapi": "VAPI_API_KEY",
        "bland": "BLAND_API_KEY",
        "elevenlabs": "ELEVENLABS_API_KEY",
        "synthflow": "SYNTHFLOW_API_KEY",
        "bolna": "BOLNA_API_KEY",
        "livekit": "LIVEKIT_API_KEY",
    }
    return mapping.get(plat)


def fill_suite_scenarios(
    suite: SuiteConfig,
    *,
    categories: list[str] | None = None,
    tests_per_category: int = 5,
    purpose: str = "",
    agent_name: str = "agent",
    model: str | None = None,
    agent_brief: dict[str, Any] | None = None,
    on_progress: ProgressCallback | None = None,
) -> SuiteConfig:
    """Replace personas/scenarios on an existing suite; keep agent / models / speech."""
    generated = generate_suite(
        platform=suite.agent.platform or "custom",
        agent_id=suite.agent.agent_id,
        agent_name=agent_name,
        purpose=purpose,
        categories=categories,
        tests_per_category=tests_per_category,
        transport=suite.agent.transport.value,
        model=model or suite.models.simulator,
        agent_brief=agent_brief,
        on_progress=on_progress,
    )
    suite.personas = generated.personas
    suite.scenarios = generated.scenarios
    return suite


__all__ = [
    "CATEGORY_CATALOG",
    "DEFAULT_CATEGORIES",
    "MAX_TESTS_PER_CATEGORY",
    "ProgressCallback",
    "fill_suite_scenarios",
    "generate_suite",
    "list_categories",
    "llm_generate_category_tests",
    "parse_categories",
]
