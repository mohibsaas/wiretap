"""Simulator config overlay — onboard speech must win over suite YAML snapshot."""

from __future__ import annotations

from pathlib import Path

from wiretap.models import Persona, Scenario, SuiteConfig
from wiretap.services.onboard import (
    apply_simulator_config,
    configure_caller,
    sync_simulator_config_to_suites,
)
from wiretap.suite import dump_suite, load_suite


def _minimal_suite(*, stt: str = "pyai", tts: str = "pyai", voice: str = "alloy") -> SuiteConfig:
    return SuiteConfig(
        personas=[
            Persona(
                id="p1",
                identity="caller",
                goal="cancel",
                personality="direct",
            )
        ],
        scenarios=[
            Scenario(
                id="s1",
                name="Cancel",
                persona_id="p1",
                success_criteria="cancelled",
            )
        ],
        speech={"stt": stt, "tts": tts, "voice": voice},
        models={"simulator": "gpt-4o-mini", "judge": "gpt-4o-mini"},
    )


def test_apply_simulator_config_overlays_speech(tmp_path: Path) -> None:
    configure_caller(
        llm_provider="openai",
        llm_api_key="sk-test",
        stt="deepgram",
        tts="cartesia",
        voice="sonic",
        stt_api_key="dg-test",
        tts_api_key="cart-test",
        cwd=tmp_path,
    )
    suite = _minimal_suite(stt="openai", tts="openai", voice="fable")
    apply_simulator_config(suite, tmp_path)
    assert suite.speech.stt == "deepgram"
    assert suite.speech.tts == "cartesia"
    assert suite.speech.voice == "sonic"


def test_configure_syncs_suite_yaml(tmp_path: Path) -> None:
    suites = tmp_path / ".wiretap" / "suites"
    suites.mkdir(parents=True)
    path = suites / "demo.yaml"
    dump_suite(_minimal_suite(stt="openai", tts="openai", voice="fable"), path)

    result = configure_caller(
        llm_provider="openai",
        llm_api_key="sk-test",
        simulator_model="gpt-4o",
        judge_model="gpt-4o",
        stt="deepgram",
        tts="elevenlabs",
        voice="Rachel",
        stt_api_key="dg-test",
        tts_api_key="el-test",
        cwd=tmp_path,
    )
    assert "demo" in (result.get("suites_synced") or [])
    suite = load_suite(path)
    assert suite.speech.stt == "deepgram"
    assert suite.speech.tts == "elevenlabs"
    assert suite.speech.voice == "Rachel"
    assert suite.models.simulator == "gpt-4o"
    # Second sync is a no-op when already matched
    assert sync_simulator_config_to_suites(tmp_path) == []
