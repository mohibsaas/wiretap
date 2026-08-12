"""Simulate one scenario in isolation."""

from __future__ import annotations

import uuid
from pathlib import Path

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


async def simulate_scenario(
    suite: SuiteConfig,
    scenario: Scenario,
    *,
    suite_id: str = "default",
    batch_id: str = "",
    cwd: Path | None = None,
) -> SimulationArtifact:
    persona = _persona(suite, scenario.persona_id)
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

    try:
        for _ in range(scenario.max_turns):
            inbound = await transport.receive()
            if inbound.hung_up:
                break
            if inbound.text:
                transcript.append(TurnRecord(role="agent", text=inbound.text))
                orchestrator.observe_agent(inbound.text)

            text, hangup = orchestrator.next_utterance()
            if text:
                transcript.append(orchestrator.as_turn(text))
                await transport.send_text(text)
            if hangup:
                break
    finally:
        await transport.hangup()

    orch_meta = orchestrator.describe()
    simulation_id = uuid.uuid4().hex
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
        save_simulation(artifact, cwd)
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

    save_simulation(artifact, cwd)
    return artifact


def _persona(suite: SuiteConfig, persona_id: str) -> Persona:
    for p in suite.personas:
        if p.id == persona_id:
            return p
    raise KeyError(f"Unknown persona_id: {persona_id}")
