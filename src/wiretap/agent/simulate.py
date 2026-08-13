"""Simulate one scenario in isolation."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from wiretap.agent.events import ProgressHandler, SimEvent, SimPhase, truncate
from wiretap.agent.orchestrator import build_orchestrator
from wiretap.agent.beats import beat_for_turn
from wiretap.eval import check_caller_contract, judge_call, run_rules
from wiretap.eval.judge import DEFAULT_PASS_THRESHOLD
from wiretap.models import (
    JudgeResult,
    Persona,
    Scenario,
    SimulationArtifact,
    SuiteConfig,
    TurnRecord,
)
from wiretap.providers.speech import suggest_pyai_if_unconfigured
from wiretap.providers.tts import prefetch_pcm
from wiretap.suite import latest_baseline, regression_failed, save_simulation
from wiretap.suite.audio import CallRecorder, save_call_audio
from wiretap.transport import build_transport
from wiretap.transport.transcript_util import pick_judge_transcript


def _playback_turns(turns: list[TurnRecord]) -> list[dict[str, Any]]:
    """WAV-aligned turns for UI scrubbing (survives provider_final transcript swap)."""
    out: list[dict[str, Any]] = []
    for t in turns:
        if t.start_ms is None or t.end_ms is None:
            continue
        out.append(
            {
                "role": t.role,
                "text": t.text,
                "start_ms": t.start_ms,
                "end_ms": t.end_ms,
            }
        )
    return out


def _emit(
    on_progress: ProgressHandler | None,
    *,
    phase: SimPhase,
    scenario: Scenario,
    detail: str = "",
    turn: int = 0,
    role: str | None = None,
    text: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    if on_progress is None:
        return
    on_progress(
        SimEvent(
            phase=phase,
            scenario_id=scenario.id,
            scenario_name=(scenario.name or scenario.id).strip(),
            detail=detail,
            turn=turn,
            role=role,
            text=text,
            extra=extra or {},
        )
    )


async def simulate_scenario(
    suite: SuiteConfig,
    scenario: Scenario,
    *,
    suite_id: str = "default",
    batch_id: str = "",
    cwd: Path | None = None,
    on_progress: ProgressHandler | None = None,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
) -> SimulationArtifact:
    persona = _persona(suite, scenario.persona_id)
    platform = suite.agent.platform or "local"
    _emit(
        on_progress,
        phase="connecting",
        scenario=scenario,
        detail=f"connecting via {platform}…",
    )

    transport = build_transport(suite.agent)
    recorder = CallRecorder(sample_rate=16_000)
    attach = getattr(transport, "attach_recorder", None)
    if callable(attach):
        attach(recorder)
    configure = getattr(transport, "configure_speech", None)
    if callable(configure):
        configure(
            stt=suite.speech.stt,
            tts=suite.speech.tts,
            voice=suite.speech.voice,
        )

    if suite.agent.transport.value != "text":
        suggest_pyai_if_unconfigured(suite.speech.stt, suite.speech.tts)

    temp = 0.2 if suite.mode.strict else suite.mode.temperature
    orchestrator = build_orchestrator(
        persona=persona,
        success_criteria=scenario.success_criteria,
        model=suite.models.simulator,
        phases=scenario.flow_phases or None,
        beats=scenario.beats,
        temperature=temp,
        stt=suite.speech.stt,
        tts=suite.speech.tts,
        voice=suite.speech.voice,
    )

    baseline = latest_baseline(scenario.id, cwd)
    transcript: list[TurnRecord] = []
    await transport.connect(suite.agent)
    # Hide first-reply TTS RTT behind the agent's greeting.
    first_beat = beat_for_turn(list(scenario.beats or []), 1)
    if first_beat and first_beat.say:
        prefetch_pcm(
            first_beat.say,
            voice=suite.speech.voice or "alloy",
            provider=suite.speech.tts,
        )
    _emit(
        on_progress,
        phase="waiting_agent",
        scenario=scenario,
        detail="connected — waiting for agent…",
    )

    try:
        for _ in range(scenario.max_turns):
            inbound = await transport.receive()
            if inbound.hung_up:
                break
            if inbound.text:
                transcript.append(
                    TurnRecord(
                        role="agent",
                        text=inbound.text,
                        start_ms=inbound.start_ms,
                        end_ms=inbound.end_ms,
                    )
                )
                orchestrator.observe_agent(inbound.text)
                _emit(
                    on_progress,
                    phase="turn",
                    scenario=scenario,
                    turn=len(transcript),
                    role="agent",
                    text=inbound.text,
                    detail=truncate(inbound.text),
                )

            text, hangup = await orchestrator.next_utterance()
            if text:
                # Overlap TTS with progress emit / transport mute setup.
                prefetch_pcm(
                    text,
                    voice=suite.speech.voice or "alloy",
                    provider=suite.speech.tts,
                )
                t0 = recorder.elapsed_ms()
                await transport.send_text(text)
                t1 = recorder.elapsed_ms()
                turn = orchestrator.as_turn(text)
                turn.start_ms = t0
                turn.end_ms = max(t1, t0)
                transcript.append(turn)
                _emit(
                    on_progress,
                    phase="turn",
                    scenario=scenario,
                    turn=len(transcript),
                    role="user",
                    text=text,
                    detail=truncate(text),
                )
            if hangup:
                break
    finally:
        _emit(on_progress, phase="hanging_up", scenario=scenario)
        await transport.hangup()

    live_transcript = list(transcript)
    transcript_source = "live"
    # Prefer provider post-call transcript when available — but not when it
    # missed the caller or is clearly more fragmented than live STT.
    fetch_final = getattr(transport, "fetch_final_transcript", None)
    if callable(fetch_final):
        try:
            official = await fetch_final()
        except Exception:
            official = None
        if official:
            transcript, transcript_source = pick_judge_transcript(
                live_transcript, official
            )
            _emit(
                on_progress,
                phase="judging",
                scenario=scenario,
                detail=f"using {transcript_source} transcript…",
            )

    orch_meta = orchestrator.describe()
    simulation_id = uuid.uuid4().hex
    _emit(on_progress, phase="judging", scenario=scenario, detail="checking rules + judge…")
    audio_rel = save_call_audio(simulation_id, recorder, cwd)
    persona_title = (persona.name or persona.identity or persona.id).strip()
    scenario_title = (scenario.name or scenario.id).strip()

    violations = check_caller_contract(
        persona=persona,
        turns=live_transcript,
        strict=suite.mode.strict,
    )
    if violations:
        gate = getattr(transport, "_gate", None)
        gate_err = getattr(gate, "last_error", None) if gate is not None else None
        harness_fault = any("never heard agent speech" in v for v in violations)
        reason_prefix = (
            "Inconclusive: harness could not hear the agent — "
            if harness_fault
            else "Inconclusive: test agent broke contract — "
        )
        artifact = SimulationArtifact(
            simulation_id=simulation_id,
            batch_id=batch_id,
            suite_id=suite_id,
            scenario_id=scenario.id,
            scenario_name=scenario_title,
            persona_id=persona.id,
            persona_name=persona_title,
            passed=False,
            transcript=transcript,
            judge=JudgeResult(
                passed=False,
                reason=reason_prefix + "; ".join(violations),
                suggestions=[],
            ),
            rules=run_rules(transcript, scenario.rules),
            metrics={"turns": len(transcript)},
            meta={
                "transport": suite.agent.transport.value,
                "orchestrator": orch_meta,
                "inconclusive": True,
                "simulator_invalid": violations,
                "harness_fault": harness_fault,
                "live_turn_count": len(live_transcript),
                "live_agent_turns": sum(1 for t in live_transcript if t.role == "agent"),
                "live_user_turns": sum(1 for t in live_transcript if t.role == "user"),
                "transcript_source": transcript_source,
                "stt_last_error": gate_err,
                "agent_id": suite.agent.agent_id,
                "platform": suite.agent.platform,
                "playback_turns": _playback_turns(live_transcript),
            },
            audio_path=audio_rel,
        )
        _emit(on_progress, phase="saving", scenario=scenario)
        save_simulation(artifact, cwd)
        _emit(
            on_progress,
            phase="finished",
            scenario=scenario,
            detail=artifact.judge.reason,
            extra={"result": "INCONCLUSIVE", "reason": artifact.judge.reason},
        )
        return artifact

    rules = run_rules(transcript, scenario.rules)
    judge = await judge_call(
        model=suite.models.judge,
        turns=transcript,
        success_criteria=scenario.success_criteria,
        rubric=scenario.rubric,
        goal=persona.goal,
        scenario_name=scenario_title,
        pass_threshold=pass_threshold,
        judge_config=suite.judge,
    )
    # Deterministic rules can still fail a goal-pass.
    if not rules.passed and judge.passed:
        judge.passed = False
        judge.verdict = "fail"
        judge.suggestions = judge.suggestions or [
            f"Fix rule failure: {f}" for f in rules.failures
        ]
    passed = bool(rules.passed and judge.passed)
    if passed:
        judge.suggestions = []
        judge.verdict = "pass"

    meta: dict[str, Any] = {
        "transport": suite.agent.transport.value,
        "orchestrator": orch_meta,
        "agent_id": suite.agent.agent_id,
        "platform": suite.agent.platform,
        "transcript_source": transcript_source,
        "pass_threshold": pass_threshold,
        "fail_below": judge.fail_below,
        "pass_at": judge.pass_at,
        "pass_mode": judge.pass_mode,
        "verdict": judge.verdict,
        "goal_match_pct": (
            round(float(judge.score) * 100.0, 1) if judge.score is not None else None
        ),
        "playback_turns": _playback_turns(live_transcript),
    }
    if live_transcript is not transcript:
        meta["live_turn_count"] = len(live_transcript)

    artifact = SimulationArtifact(
        simulation_id=simulation_id,
        batch_id=batch_id,
        suite_id=suite_id,
        scenario_id=scenario.id,
        scenario_name=scenario_title,
        persona_id=persona.id,
        persona_name=persona_title,
        passed=passed,
        transcript=transcript,
        judge=judge,
        rules=rules,
        metrics={"turns": len(transcript)},
        meta=meta,
        audio_path=audio_rel,
    )
    if regression_failed(artifact, baseline):
        artifact.meta["regression"] = True
        artifact.passed = False
        artifact.judge.verdict = "fail"
        if not artifact.judge.suggestions:
            artifact.judge.suggestions = [
                "Regressed vs previous passing baseline for this scenario."
            ]

    _emit(on_progress, phase="saving", scenario=scenario)
    save_simulation(artifact, cwd)
    if artifact.meta.get("inconclusive"):
        result = "INCONCLUSIVE"
    elif artifact.passed:
        result = "PASS"
    elif (artifact.judge.verdict or "").lower() == "partial":
        result = "PARTIAL"
    else:
        result = "FAIL"
    pct = ""
    if artifact.judge.score is not None and not artifact.meta.get("inconclusive"):
        pct = f"{round(float(artifact.judge.score) * 100)}% goal match"
    reason = pct or artifact.judge.reason
    if pct and artifact.judge.reason:
        reason = f"{pct} — {artifact.judge.reason}"
    _emit(
        on_progress,
        phase="finished",
        scenario=scenario,
        detail=artifact.judge.reason,
        extra={"result": result, "reason": reason},
    )
    return artifact


def _persona(suite: SuiteConfig, persona_id: str) -> Persona:
    from wiretap.prompts.caller_knowledge import enrich_persona_knowledge

    for p in suite.personas:
        if p.id == persona_id:
            # Ensure ZIP/phone exist even for older suites with empty knowledge.
            enriched = enrich_persona_knowledge(p.knowledge)
            if enriched != dict(p.knowledge or {}):
                return p.model_copy(update={"knowledge": enriched})
            return p
    raise KeyError(f"Unknown persona_id: {persona_id}")
