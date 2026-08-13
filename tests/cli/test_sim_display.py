"""Unit tests for simulate progress display."""

from __future__ import annotations

from rich.console import Console

from wiretap.agent.events import SimEvent, truncate
from wiretap.cli.sim_display import (
    SimulateDisplay,
    print_fail_details,
    print_run_summary,
)
from wiretap.models import JudgeResult, RuleResult, SimulationArtifact


def test_truncate() -> None:
    assert truncate("hi") == "hi"
    assert len(truncate("x" * 100, 20)) == 20
    assert truncate("x" * 100, 20).endswith("…")


def test_display_event_flow() -> None:
    console = Console(force_terminal=False, width=100, record=True)
    display = SimulateDisplay(
        suite_label="demo.yaml",
        agent_label="agent_1",
        platform="retell",
        batch_id="abc",
        total=1,
        console=console,
    )
    display.add_scenario("s1", "Emotional case 1")
    display.on_event(
        SimEvent(phase="queued", scenario_id="s1", scenario_name="Emotional case 1")
    )
    display.on_event(
        SimEvent(phase="connecting", scenario_id="s1", detail="connecting via retell…")
    )
    display.on_event(
        SimEvent(
            phase="turn",
            scenario_id="s1",
            turn=1,
            role="agent",
            text="Hello, how can I help?",
        )
    )
    display.on_event(
        SimEvent(
            phase="finished",
            scenario_id="s1",
            extra={"result": "PASS", "reason": "Goal met"},
        )
    )
    row = display.rows["s1"]
    assert row.state == "finished"
    assert row.result == "PASS"
    assert row.turns == 1
    # Render should not raise
    rendered = display._render()
    assert rendered is not None


def test_print_fail_details_renders_goal_match() -> None:
    console = Console(force_terminal=False, width=100, record=True)
    art = SimulationArtifact(
        simulation_id="sim1",
        suite_id="demo",
        scenario_id="angry",
        scenario_name="Angry project delay",
        persona_id="p1",
        passed=False,
        transcript=[],
        judge=JudgeResult(
            passed=False,
            score=0.52,
            verdict="partial",
            reason="Agent did not de-escalate fully.",
            pass_mode="goal_match",
            fail_below=0.5,
            pass_at=0.7,
            suggestions=["Acknowledge anger before asking for zip."],
        ),
        rules=RuleResult(passed=True, failures=[]),
    )
    print_fail_details(art, console=console)
    text = console.export_text()
    assert "Angry project delay" in text
    assert "52%" in text or "Goal match" in text
    assert "PARTIAL" in text
    assert "Improve" in text
    assert "Acknowledge anger" in text


def test_print_run_summary() -> None:
    console = Console(force_terminal=False, width=100, record=True)
    print_run_summary(
        passed=2,
        failed=3,
        partial=1,
        inconclusive=1,
        total=7,
        batch_id="batch123",
        console=console,
    )
    text = console.export_text()
    assert "2 pass" in text
    assert "3 fail" in text
    assert "1 partial" in text
    assert "batch123" in text
