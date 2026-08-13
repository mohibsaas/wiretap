"""Rich live progress UI for `wiretap simulate`."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal, Self

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from wiretap.agent.events import SimEvent, truncate

RowState = Literal[
    "queued",
    "connecting",
    "waiting_agent",
    "turn",
    "hanging_up",
    "judging",
    "saving",
    "finished",
    "failed",
]


@dataclass
class ScenarioRow:
    scenario_id: str
    title: str
    state: RowState = "queued"
    detail: str = ""
    turns: int = 0
    result: str | None = None  # PASS | FAIL | INCONCLUSIVE
    reason: str = ""
    started_at: float | None = None
    finished_at: float | None = None


@dataclass
class SimulateDisplay:
    """Live terminal board for a suite evaluation run."""

    suite_label: str
    agent_label: str
    platform: str
    batch_id: str
    total: int
    console: Console = field(default_factory=Console)
    rows: dict[str, ScenarioRow] = field(default_factory=dict)
    _live: Live | None = field(default=None, repr=False)
    _overall: Progress | None = field(default=None, repr=False)
    _overall_task: int | None = field(default=None, repr=False)
    _done_count: int = 0

    def add_scenario(self, scenario_id: str, title: str) -> None:
        self.rows[scenario_id] = ScenarioRow(scenario_id=scenario_id, title=title)

    def __enter__(self) -> Self:
        self._overall = Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=28),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=self.console,
            transient=False,
        )
        self._overall_task = self._overall.add_task("Evaluating", total=self.total)
        self._live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=8,
            transient=False,
        )
        self._live.start()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._live is not None:
            self._live.update(self._render())
            self._live.stop()
            self._live = None

    def on_event(self, event: SimEvent) -> None:
        row = self.rows.get(event.scenario_id)
        if row is None:
            row = ScenarioRow(
                scenario_id=event.scenario_id,
                title=event.scenario_name or event.scenario_id,
            )
            self.rows[event.scenario_id] = row

        if event.scenario_name:
            row.title = event.scenario_name

        if event.phase == "queued":
            row.state = "queued"
            row.detail = "waiting for slot"
        elif event.phase == "connecting":
            row.state = "connecting"
            row.detail = event.detail or "dialing live agent…"
            row.started_at = row.started_at or time.monotonic()
        elif event.phase == "waiting_agent":
            row.state = "waiting_agent"
            row.detail = event.detail or "waiting for agent speech…"
        elif event.phase == "turn":
            row.state = "turn"
            row.turns = max(row.turns, event.turn)
            who = "agent" if event.role == "agent" else "caller"
            preview = truncate(event.text or event.detail, 64)
            row.detail = f"turn {event.turn} · {who}: {preview}" if preview else f"turn {event.turn}"
        elif event.phase == "hanging_up":
            row.state = "hanging_up"
            row.detail = "hanging up…"
        elif event.phase == "judging":
            row.state = "judging"
            row.detail = event.detail or "scoring with judge…"
        elif event.phase == "saving":
            row.state = "saving"
            row.detail = "saving artifact…"
        elif event.phase == "finished":
            row.state = "finished"
            row.finished_at = time.monotonic()
            row.result = str(event.extra.get("result") or "PASS")
            row.reason = truncate(str(event.extra.get("reason") or event.detail), 90)
            row.detail = row.reason
            self._bump_overall()
        elif event.phase == "failed":
            row.state = "failed"
            row.finished_at = time.monotonic()
            row.result = "ERROR"
            row.reason = truncate(event.detail or "failed", 90)
            row.detail = row.reason
            self._bump_overall()

        if self._live is not None:
            self._live.update(self._render())

    def _bump_overall(self) -> None:
        self._done_count += 1
        if self._overall is not None and self._overall_task is not None:
            self._overall.update(self._overall_task, completed=self._done_count)

    def _render(self) -> Group:
        header = Text.assemble(
            ("Suite ", "dim"),
            (self.suite_label, "bold cyan"),
            ("  ·  ", "dim"),
            ("agent ", "dim"),
            (self.agent_label, "cyan"),
            ("  ·  ", "dim"),
            (self.platform or "local", "magenta"),
            "\n",
            ("Evaluation ", "dim"),
            (self.batch_id, "cyan"),
        )

        table = Table(
            show_header=True,
            header_style="bold dim",
            box=None,
            pad_edge=False,
            expand=True,
            padding=(0, 1),
        )
        table.add_column("", width=2, no_wrap=True)
        table.add_column("Scenario", ratio=2, overflow="ellipsis")
        table.add_column("Status", ratio=3, overflow="ellipsis")
        table.add_column("Turns", justify="right", width=5)
        table.add_column("Time", justify="right", width=6)

        for row in self.rows.values():
            icon, status_text = self._status_cell(row)
            elapsed = ""
            if row.started_at is not None:
                end = row.finished_at or time.monotonic()
                elapsed = f"{end - row.started_at:0.0f}s"
            table.add_row(
                icon,
                row.title,
                status_text,
                str(row.turns) if row.turns else "—",
                elapsed or "—",
            )

        body = Panel(table, border_style="dim", padding=(0, 1))
        footer = self._overall if self._overall is not None else Text("")
        return Group(header, "", body, "", footer)

    def _status_cell(self, row: ScenarioRow) -> tuple[str, Text]:
        spin = self._spin_frame()
        if row.state == "queued":
            return "○", Text(row.detail or "queued", style="dim")
        if row.state == "connecting":
            return spin, Text(row.detail or "connecting…", style="cyan")
        if row.state == "waiting_agent":
            return spin, Text(row.detail or "waiting…", style="cyan")
        if row.state == "turn":
            return "●", Text(row.detail, style="white")
        if row.state in {"hanging_up", "judging", "saving"}:
            return spin, Text(row.detail, style="yellow")
        if row.state == "finished":
            if row.result == "PASS":
                return "✔", Text.assemble(
                    ("PASS", "bold green"),
                    ("  ", ""),
                    (row.reason, "dim"),
                )
            if row.result == "INCONCLUSIVE":
                return "!", Text.assemble(
                    ("INCONCLUSIVE", "bold yellow"),
                    ("  ", ""),
                    (row.reason, "dim"),
                )
            return "✖", Text.assemble(
                ("FAIL", "bold red"),
                ("  ", ""),
                (row.reason, "dim"),
            )
        if row.state == "failed":
            return "✖", Text.assemble(
                ("ERROR", "bold red"),
                ("  ", ""),
                (row.reason, "dim"),
            )
        return "·", Text(row.detail or row.state)

    @staticmethod
    def _spin_frame() -> str:
        frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        return frames[int(time.monotonic() * 10) % len(frames)]

