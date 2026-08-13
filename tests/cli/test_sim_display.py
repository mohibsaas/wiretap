"""Unit tests for simulate progress display."""

from __future__ import annotations

from rich.console import Console

from wiretap.agent.events import SimEvent, truncate
from wiretap.cli.sim_display import SimulateDisplay


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
