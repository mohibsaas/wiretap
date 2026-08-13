"""Simulate one scenario in isolation."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from wiretap.agent.events import ProgressHandler, SimEvent, SimPhase, truncate
from wiretap.agent.orchestrator import build_orchestrator
from wiretap.eval import check_caller_contract, judge_call, run_rules
from wiretap.models import (
    JudgeResult,
    Persona,
    Scenario,
    SimulationArtifact,
    SuiteConfig,
    TurnRecord,
)
from wiretap.providers.speech import suggest_pyai_if_unconfigured
from wiretap.suite import latest_baseline, regression_failed, save_simulation
from wiretap.suite.audio import CallRecorder, save_call_audio
from wiretap.transport import build_transport


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
                transcript.append(TurnRecord(role="agent", text=inbound.text))
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

            text, hangup = orchestrator.next_utterance()
            if text:
                transcript.append(orchestrator.as_turn(text))
                _emit(
                    on_progress,
                    phase="turn",
                    scenario=scenario,
                    turn=len(transcript),
                    role="user",
                    text=text,
                    detail=truncate(text),
                )
                await transport.send_text(text)
            if hangup:
                break
    finally:
        _emit(on_progress, phase="hanging_up", scenario=scenario)
        await transport.hangup()

    orch_meta = orchestrator.describe()
    simulation_id = uuid.uuid4().hex
    _emit(on_progress, phase="judging", scenario=scenario, detail="checking rules + judge…")
    audio_rel = save_call_audio(simulation_id, recorder, cwd)
    persona_title = (persona.name or persona.identity or persona.id).strip()
    scenario_title = (scenario.name or scenario.id).strip()

    violations = check_caller_contract(
        persona=persona,
        turns=transcript,
        strict=suite.mode.strict,
    )
    if violations:
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
                reason="Inconclusive: test agent broke contract — "
                + "; ".join(violations),
                suggestions=[],
            ),
            rules=run_rules(transcript, scenario.rules),
            metrics={"turns": len(transcript)},
            meta={
                "transport": suite.agent.transport.value,
                "orchestrator": orch_meta,
                "inconclusive": True,
                "simulator_invalid": violations,
                "agent_id": suite.agent.agent_id,
                "platform": suite.agent.platform,
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
    judge = judge_call(
        model=suite.models.judge,
        turns=transcript,
        success_criteria=scenario.success_criteria,
        rubric=scenario.rubric,
    )
    passed = bool(rules.passed and judge.passed)
    if not rules.passed and judge.passed:
        judge.passed = False
        judge.suggestions = judge.suggestions or [
            f"Fix rule failure: {f}" for f in rules.failures
        ]
    if passed:
        judge.suggestions = []

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
        meta={
            "transport": suite.agent.transport.value,
            "orchestrator": orch_meta,
            "agent_id": suite.agent.agent_id,
            "platform": suite.agent.platform,
        },
        audio_path=audio_rel,
    )
    if regression_failed(artifact, baseline):
        artifact.meta["regression"] = True
        artifact.passed = False
        if not artifact.judge.suggestions:
            artifact.judge.suggestions = [
                "Regressed vs previous passing baseline for this scenario."
            ]

    _emit(on_progress, phase="saving", scenario=scenario)
    save_simulation(artifact, cwd)
    result = "PASS" if artifact.passed else "FAIL"
    if artifact.meta.get("inconclusive"):
        result = "INCONCLUSIVE"
    _emit(
        on_progress,
        phase="finished",
        scenario=scenario,
        detail=artifact.judge.reason,
        extra={"result": result, "reason": artifact.judge.reason},
    )
    return artifact


def _persona(suite: SuiteConfig, persona_id: str) -> Persona:
    for p in suite.personas:
        if p.id == persona_id:
            return p
    raise KeyError(f"Unknown persona_id: {persona_id}")
