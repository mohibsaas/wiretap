"""Run-level advice — what to change about the agent, not this call.

One LLM call per evaluation run, after every scenario is judged. Scoring stays
in ``eval.judge`` and never sees the agent's configuration, so a verdict can
never be softened by the agent's own instructions; the advisor sees the config
summary but treats those verdicts as settled input.

Additive by design: any failure here returns advice carrying an ``error`` and
never disturbs the run.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wiretap.eval.tools import CAPTURE_OK
from wiretap.models import (
    AdviceEvidence,
    AdviceFinding,
    RunAdvice,
    SimulationArtifact,
    SuiteConfig,
)
from wiretap.prompts.advisor import (
    MAX_FINDINGS,
    TARGETS,
    advisor_system_prompt,
    advisor_user_message,
)
from wiretap.providers.llm import acomplete
from wiretap.services.agent_brief import sanitize_text

# Enough calls to expose a pattern without paying for the whole run's context.
MAX_CALLS = 12
HEAD_TURNS = 2
TAIL_TURNS = 8
TURN_CAP = 300
QUOTE_CAP = 140
TEXT_CAP = 600

_SEVERITY = ("high", "medium", "low")
_CONFIDENCE = ("high", "medium", "low")
# Suite-level opt-out, for runs that do not want to pay for the extra call.
_DISABLED = {"off", "none", "disabled", "false"}

# What the advisor is allowed to see of the agent. ``prompt_excerpt`` is
# deliberately absent: advice is grounded in the heuristic summary instead, so a
# finding can never quote a customer's system prompt back into a stored
# artifact. Flow nodes are reduced to structure for the same reason.
_CONFIG_FIELDS = (
    "agent_name",
    "purpose",
    "summary",
    "tools",
    "irreversible_tools",
    "first_message",
    "language",
    "end_call_phrases",
    "platform",
)
_FLOW_NODE_FIELDS = {"id", "type", "name"}


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def advisor_config(brief: dict[str, Any] | None) -> dict[str, Any]:
    """Narrow an agent brief to the fields the advisor may reason from."""
    if not brief:
        return {}
    out: dict[str, Any] = {k: brief[k] for k in _CONFIG_FIELDS if brief.get(k)}
    nodes = brief.get("flow_nodes") or []
    trimmed = [
        {k: v for k, v in node.items() if k in _FLOW_NODE_FIELDS}
        for node in nodes
        if isinstance(node, dict)
    ]
    if trimmed:
        out["flow_nodes"] = trimmed
    return out


def needs_attention(artifact: SimulationArtifact) -> bool:
    """Failed or partial, and the harness actually heard the call."""
    if artifact.meta.get("inconclusive"):
        return False
    return not artifact.passed


def _verdict(artifact: SimulationArtifact) -> str:
    return (artifact.judge.verdict or ("pass" if artifact.passed else "fail")).lower()


def _rank(artifact: SimulationArtifact) -> tuple[int, float]:
    """Worst first: fails before partials, then by score."""
    score = artifact.judge.score if artifact.judge.score is not None else 0.0
    return (0 if _verdict(artifact) == "fail" else 1, float(score))


def _transcript_excerpt(artifact: SimulationArtifact) -> list[str]:
    """Opening turns plus the ending, where goal failures usually surface."""
    turns = artifact.transcript
    if len(turns) <= HEAD_TURNS + TAIL_TURNS:
        selected: list[Any] = list(turns)
        elided = 0
    else:
        selected = list(turns[:HEAD_TURNS]) + list(turns[-TAIL_TURNS:])
        elided = len(turns) - HEAD_TURNS - TAIL_TURNS
    out: list[str] = []
    for i, turn in enumerate(selected):
        if elided and i == HEAD_TURNS:
            out.append(f"… {elided} turns omitted …")
        who = "Caller" if turn.role == "user" else "Agent"
        text = (turn.text or "").strip()
        if len(text) > TURN_CAP:
            text = text[:TURN_CAP].rstrip() + "…"
        out.append(f"{who}: {text}")
    return out


def _call_digest(artifact: SimulationArtifact) -> dict[str, Any]:
    metrics = artifact.metrics or {}
    digest: dict[str, Any] = {
        "scenario_id": artifact.scenario_id,
        "scenario_name": artifact.scenario_name,
        "verdict": _verdict(artifact),
        "goal_match_pct": (
            round(float(artifact.judge.score) * 100)
            if artifact.judge.score is not None
            else None
        ),
        "judge_reason": artifact.judge.reason,
        "transcript_excerpt": _transcript_excerpt(artifact),
    }
    if artifact.judge.suggestions:
        digest["judge_suggestions"] = artifact.judge.suggestions
    # missing_tools is computed for every call, but on platforms that expose no
    # tool history every expected tool looks missing. Advising on that would
    # blame the agent for our blind spot.
    if str(artifact.meta.get("tool_capture") or "") == CAPTURE_OK:
        if metrics.get("missing_tools"):
            digest["tools_never_called"] = metrics["missing_tools"]
        if metrics.get("unexpected_tools"):
            digest["tools_called_unexpectedly"] = metrics["unexpected_tools"]
    if not artifact.rules.passed and artifact.rules.failures:
        digest["rule_failures"] = artifact.rules.failures
    return digest


def _run_summary(
    artifacts: list[SimulationArtifact], *, suite_id: str
) -> dict[str, Any]:
    return {
        "suite_id": suite_id,
        "total_calls": len(artifacts),
        "passed": sum(1 for a in artifacts if a.passed and not a.meta.get("inconclusive")),
        "partial": sum(
            1
            for a in artifacts
            if not a.passed
            and _verdict(a) == "partial"
            and not a.meta.get("inconclusive")
        ),
        "failed": sum(
            1
            for a in artifacts
            if not a.passed
            and _verdict(a) == "fail"
            and not a.meta.get("inconclusive")
        ),
        "inconclusive": sum(1 for a in artifacts if a.meta.get("inconclusive")),
    }


async def advise_run(
    *,
    model: str,
    artifacts: list[SimulationArtifact],
    suite_id: str = "",
    agent_config: dict[str, Any] | None = None,
) -> RunAdvice | None:
    """Advice for one run, or None when there is nothing worth advising on."""
    attention = sorted(
        [a for a in artifacts if needs_attention(a)], key=_rank
    )[:MAX_CALLS]
    if not attention:
        return None

    config = advisor_config(agent_config)
    has_config = bool(config)
    advice = RunAdvice(
        model=model,
        generated_at=_now_iso(),
        grounding="config" if has_config else "behavior_only",
        based_on_scenarios=[a.scenario_id for a in attention],
    )
    try:
        raw = await acomplete(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": advisor_system_prompt(has_config=has_config),
                },
                {
                    "role": "user",
                    "content": advisor_user_message(
                        run=_run_summary(artifacts, suite_id=suite_id),
                        calls=[_call_digest(a) for a in attention],
                        agent_config=config or None,
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=1600,
        )
    except Exception as exc:  # noqa: BLE001 — advice must never break a run
        advice.error = f"{type(exc).__name__}: {exc}"[:200]
        return advice

    data = _parse_json(raw)
    if data is None:
        advice.error = f"Advisor returned non-JSON: {raw[:160]}"
        return advice

    advice.summary = _clean(data.get("summary"), cap=TEXT_CAP)
    advice.findings = _findings(data.get("findings"), has_config=has_config)
    return advice


async def advise_for_run(
    cfg: SuiteConfig,
    artifacts: list[SimulationArtifact],
    *,
    suite_id: str,
    cwd: Path | None = None,
) -> RunAdvice | None:
    """Advice for a finished run, resolving the model and brief from the suite.

    Returns None when the suite turned the advisor off, so a run that never
    wants the extra call never pays for it.
    """
    from wiretap.services.agent_brief import brief_for_suite

    slot = (cfg.models.advisor or "").strip().lower()
    if slot in _DISABLED:
        return None

    brief: dict[str, Any] = {}
    for stem in (suite_id, cfg.agent.agent_id):
        if not stem:
            continue
        brief = brief_for_suite(str(stem), suite=cfg, cwd=cwd)
        if brief:
            break
    return await advise_run(
        model=cfg.models.advisor or cfg.models.judge,
        artifacts=artifacts,
        suite_id=suite_id,
        agent_config=brief,
    )


def _parse_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _clean(value: object, *, cap: int) -> str:
    """Strip secrets and contact details from anything we persist or render."""
    return sanitize_text(str(value or "").strip(), cap=cap)


def _one_of(value: object, allowed: tuple[str, ...], default: str) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in allowed else default


def _evidence(raw: object) -> list[AdviceEvidence]:
    if not isinstance(raw, list):
        return []
    out: list[AdviceEvidence] = []
    for item in raw[:4]:
        if isinstance(item, dict):
            quote = _clean(item.get("quote"), cap=QUOTE_CAP)
            scenario_id = str(item.get("scenario_id") or "").strip()[:120]
        else:
            quote = _clean(item, cap=QUOTE_CAP)
            scenario_id = ""
        if quote:
            out.append(AdviceEvidence(scenario_id=scenario_id, quote=quote))
    return out


def _findings(raw: object, *, has_config: bool) -> list[AdviceFinding]:
    if not isinstance(raw, list):
        return []
    out: list[AdviceFinding] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = _clean(item.get("title"), cap=160)
        evidence = _evidence(item.get("evidence"))
        # Rule 3: a finding with no transcript behind it is an opinion.
        if not title or not evidence:
            continue
        scenarios = [
            str(s).strip()[:120]
            for s in (item.get("affected_scenarios") or [])
            if str(s).strip()
        ]
        out.append(
            AdviceFinding(
                id=str(item.get("id") or "").strip()[:80] or f"finding-{len(out) + 1}",
                target=_one_of(item.get("target"), TARGETS, "agent_prompt"),
                severity=_one_of(item.get("severity"), _SEVERITY, "medium"),
                title=title,
                problem=_clean(item.get("problem"), cap=TEXT_CAP),
                recommendation=_clean(item.get("recommendation"), cap=TEXT_CAP),
                # Without the config we cannot know what the prompt already
                # says, so proposed wording would be a guess dressed as a patch.
                suggested_text=(
                    _clean(item.get("suggested_text"), cap=TEXT_CAP)
                    if has_config
                    else ""
                ),
                evidence=evidence,
                affected_scenarios=scenarios,
                confidence=_one_of(item.get("confidence"), _CONFIDENCE, "medium"),
            )
        )
        if len(out) >= MAX_FINDINGS:
            break
    return out


__all__ = [
    "MAX_CALLS",
    "advise_for_run",
    "advise_run",
    "advisor_config",
    "needs_attention",
]
