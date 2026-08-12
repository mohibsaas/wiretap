"""Agent override + call audio helpers."""

from __future__ import annotations

from pathlib import Path

from wiretap.models import (
    AgentTarget,
    Persona,
    Scenario,
    SuiteConfig,
    TransportKind,
)
from wiretap.suite.agent_override import with_agent_override
from wiretap.suite.audio import CallRecorder, save_call_audio
from wiretap.suite.loader import dump_suite


def _minimal_suite(agent_id: str, platform: str = "retell") -> SuiteConfig:
    return SuiteConfig(
        agent=AgentTarget(
            transport=TransportKind.WEBRTC,
            platform=platform,
            agent_id=agent_id,
            token_env=f"{platform.upper()}_API_KEY",
        ),
        personas=[
            Persona(id="caller", name="Test caller", identity="A caller", goal="Help")
        ],
        scenarios=[
            Scenario(
                id="smoke",
                name="Smoke",
                persona_id="caller",
                success_criteria="ok",
            )
        ],
    )


def test_with_agent_override_fields() -> None:
    suite = _minimal_suite("agent-a")
    out = with_agent_override(suite, agent_id="agent-b", platform="vapi")
    assert out.agent.agent_id == "agent-b"
    assert out.agent.platform == "vapi"
    assert out.agent.token_env == "VAPI_API_KEY"
    assert suite.agent.agent_id == "agent-a"  # original untouched


def test_with_agent_from_suite(tmp_path: Path) -> None:
    a = _minimal_suite("agent-a", "retell")
    b = _minimal_suite("agent-b", "vapi")
    (tmp_path / ".wiretap" / "suites").mkdir(parents=True, exist_ok=True)
    dump_suite(a, tmp_path / ".wiretap" / "suites" / "suite_a.yaml")
    dump_suite(b, tmp_path / ".wiretap" / "suites" / "suite_b.yaml")
    out = with_agent_override(a, agent_from="suite_b", cwd=tmp_path)
    assert out.agent.agent_id == "agent-b"
    assert out.agent.platform == "vapi"


def test_call_recorder_writes_wav(tmp_path: Path) -> None:
    rec = CallRecorder(sample_rate=16_000)
    # 100ms of silence
    rec.add(b"\x00\x00" * 1600)
    rel = save_call_audio("sim123", rec, tmp_path)
    assert rel == "simulations/audio/sim123.wav"
    path = tmp_path / ".wiretap" / rel
    assert path.is_file()
    assert path.stat().st_size > 44
