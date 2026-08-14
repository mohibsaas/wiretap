"""Rich live progress UI for `wiretap simulate`."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal, Self

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from wiretap.agent.events import SimEvent, truncate
from wiretap.cli.style import ACCENT, ERR, MUTED, OK, WARN, tool_summary

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
    concurrency: int = 1
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
            SpinnerColumn(style=ACCENT),
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=28, style=ACCENT, complete_style=ACCENT),
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
            ("◈ ", f"bold {ACCENT}"),
            ("Suite ", MUTED),
            (self.suite_label, f"bold {ACCENT}"),
            ("  ·  ", MUTED),
            ("agent ", MUTED),
            (self.agent_label, ACCENT),
            ("  ·  ", MUTED),
            (self.platform or "local", "magenta"),
            "\n",
            ("Evaluation ", MUTED),
            (self.batch_id, ACCENT),
            ("  ·  ", MUTED),
            ("concurrency ", MUTED),
            (str(self.concurrency), ACCENT),
        )

        table = Table(
            show_header=True,
            header_style=f"bold {ACCENT}",
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

        body = Panel(table, border_style=ACCENT, padding=(0, 1))
        footer = self._overall if self._overall is not None else Text("")
        return Group(header, "", body, "", footer)

    def _status_cell(self, row: ScenarioRow) -> tuple[str, Text]:
        spin = self._spin_frame()
        if row.state == "queued":
            return "○", Text(row.detail or "queued", style=MUTED)
        if row.state == "connecting":
            return spin, Text(row.detail or "connecting…", style=ACCENT)
        if row.state == "waiting_agent":
            return spin, Text(row.detail or "waiting…", style=ACCENT)
        if row.state == "turn":
            return "●", Text(row.detail, style="white")
        if row.state in {"hanging_up", "judging", "saving"}:
            return spin, Text(row.detail, style=WARN)
        if row.state == "finished":
            if row.result == "PASS":
                return "✔", Text.assemble(
                    ("PASS", f"bold {OK}"),
                    ("  ", ""),
                    (row.reason, MUTED),
                )
            if row.result == "PARTIAL":
                return "◐", Text.assemble(
                    ("PARTIAL", f"bold {WARN}"),
                    ("  ", ""),
                    (row.reason, MUTED),
                )
            if row.result == "INCONCLUSIVE":
                return "!", Text.assemble(
                    ("INCONCLUSIVE", f"bold {WARN}"),
                    ("  ", ""),
                    (row.reason, MUTED),
                )
            return "✖", Text.assemble(
                ("FAIL", f"bold {ERR}"),
                ("  ", ""),
                (row.reason, MUTED),
            )
        if row.state == "failed":
            return "✖", Text.assemble(
                ("ERROR", f"bold {ERR}"),
                ("  ", ""),
                (row.reason, MUTED),
            )
        return "·", Text(row.detail or row.state)

    @staticmethod
    def _spin_frame() -> str:
        frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        return frames[int(time.monotonic() * 10) % len(frames)]


def _goal_match_line(judge: Any) -> Text:
    """Render score as a percentage with band labels."""
    score = getattr(judge, "score", None)
    verdict = str(getattr(judge, "verdict", "") or "fail").lower()
    fail_below = float(getattr(judge, "fail_below", 0.5) or 0.5)
    pass_at = float(getattr(judge, "pass_at", 0.7) or 0.7)
    line = Text()
    if score is None:
        line.append("Goal match ", style=MUTED)
        line.append("—", style=MUTED)
        return line
    pct = round(float(score) * 100)
    color = OK if verdict == "pass" else WARN if verdict == "partial" else ERR
    line.append("Goal match ", style=MUTED)
    line.append(f"{pct}%", style=f"bold {color}")
    line.append("  ·  ", style=MUTED)
    line.append(verdict.upper(), style=f"bold {color}")
    line.append(
        f"  (fail < {round(fail_below * 100)}%  ·  "
        f"partial < {round(pass_at * 100)}%  ·  "
        f"pass ≥ {round(pass_at * 100)}%)",
        style=MUTED,
    )
    return line


def print_fail_details(art: Any, *, console: Console | None = None) -> None:
    """Pretty failure / partial card — goal match % + suggestions."""
    out = console or Console()
    title = str(
        getattr(art, "scenario_name", None)
        or getattr(art, "scenario_id", None)
        or "scenario"
    )
    judge = getattr(art, "judge", None)
    rules = getattr(art, "rules", None)
    verdict = str(getattr(judge, "verdict", "") or "fail").lower() if judge else "fail"
    is_partial = verdict == "partial"

    head = Text()
    if is_partial:
        head.append(" PARTIAL ", style=f"bold black on {WARN}")
    else:
        head.append(" FAIL ", style=f"bold white on {ERR}")
    head.append("  ")
    head.append(title, style="bold")

    parts: list[RenderableType] = [head]
    if judge is not None:
        parts.extend([Text(), _goal_match_line(judge)])
        reason = str(getattr(judge, "reason", "") or "").strip()
        if reason:
            parts.extend([Text(), Text(reason, style=MUTED)])

    failures = list(getattr(rules, "failures", None) or []) if rules else []
    if failures:
        parts.append(Text())
        parts.append(Text("Rules", style=f"bold {ACCENT}"))
        for f in failures:
            line = Text()
            line.append("  ✗ ", style=ERR)
            line.append(str(f))
            parts.append(line)

    tools = tool_summary(art)
    if tools:
        parts.append(Text())
        parts.append(Text(tools, style=MUTED))

    suggestions = list(getattr(judge, "suggestions", None) or []) if judge else []
    if suggestions:
        parts.append(Text())
        parts.append(Text("Improve", style=f"bold {ACCENT}"))
        for s in suggestions:
            line = Text()
            line.append("  → ", style=ACCENT)
            line.append(str(s).strip())
            parts.append(line)

    border = WARN if is_partial else ERR
    out.print(Panel(Group(*parts), border_style=border, padding=(0, 1)))
    out.print()


def print_pass_details(art: Any, *, console: Console | None = None) -> None:
    """Optional compact pass card with goal-match %."""
    out = console or Console()
    title = str(
        getattr(art, "scenario_name", None)
        or getattr(art, "scenario_id", None)
        or "scenario"
    )
    judge = getattr(art, "judge", None)
    head = Text()
    head.append(" PASS ", style=f"bold white on {OK}")
    head.append("  ")
    head.append(title, style="bold")
    parts: list[RenderableType] = [head]
    if judge is not None:
        parts.extend([Text(), _goal_match_line(judge)])
    out.print(Panel(Group(*parts), border_style=OK, padding=(0, 1)))
    out.print()


def print_inconclusive_details(art: Any, *, console: Console | None = None) -> None:
    """Compact inconclusive card (harness / contract)."""
    out = console or Console()
    title = str(
        getattr(art, "scenario_name", None)
        or getattr(art, "scenario_id", "")
        or "scenario"
    )
    reason = str(getattr(getattr(art, "judge", None), "reason", "") or "").strip()
    head = Text()
    head.append(" INCONCLUSIVE ", style=f"bold black on {WARN}")
    head.append("  ")
    head.append(title, style="bold")
    if reason:
        out.print(
            Panel(Group(head, Text(), Text(reason, style=MUTED)), border_style=WARN, padding=(0, 1))
        )
    else:
        out.print(Panel(head, border_style=WARN, padding=(0, 1)))
    out.print()


_TARGET_LABELS = {
    "agent_prompt": "Prompt",
    "tools": "Tools",
    "flow": "Flow",
    "voice_runtime": "Voice config",
    "test_suite": "Test suite",
}


def print_run_advice(advice: Any, *, console: Console | None = None) -> None:
    """Run-level improvement card — what to change about the agent."""
    out = console or Console()
    findings = list(getattr(advice, "findings", None) or [])
    summary = str(getattr(advice, "summary", "") or "").strip()
    if not findings and not summary:
        return

    head = Text()
    head.append("◈ ", style=f"bold {ACCENT}")
    head.append("Suggested improvements", style=f"bold {ACCENT}")
    if getattr(advice, "grounding", "") == "behavior_only":
        head.append("  ·  from call behavior only (no agent import)", style=MUTED)

    parts: list[RenderableType] = [head]
    if summary:
        parts.extend([Text(), Text(summary, style=MUTED)])

    for finding in findings:
        severity = str(getattr(finding, "severity", "medium") or "medium").lower()
        color = ERR if severity == "high" else WARN if severity == "medium" else MUTED
        target = _TARGET_LABELS.get(
            str(getattr(finding, "target", "") or ""), "Agent"
        )
        line = Text()
        line.append("\n  ● ", style=color)
        line.append(f"[{target}] ", style=MUTED)
        line.append(str(getattr(finding, "title", "") or "").strip(), style="bold")
        parts.append(line)

        recommendation = str(getattr(finding, "recommendation", "") or "").strip()
        if recommendation:
            parts.append(Text(f"      {recommendation}", style=MUTED))
        affected = list(getattr(finding, "affected_scenarios", None) or [])
        if affected:
            parts.append(
                Text(f"      Affects {len(affected)}: {', '.join(affected[:4])}", style=MUTED)
            )

    out.print(Panel(Group(*parts), border_style=ACCENT, padding=(0, 1)))
    out.print()


def print_run_summary(
    *,
    passed: int,
    failed: int,
    partial: int = 0,
    inconclusive: int,
    total: int,
    batch_id: str,
    console: Console | None = None,
) -> None:
    """Final evaluation footer matching suite/init styling."""
    out = console or Console()
    line = Text()
    line.append("◈ ", style=f"bold {ACCENT}")
    line.append("Done", style=f"bold {ACCENT}")
    line.append("  ")
    line.append(f"{passed} pass", style=f"bold {OK}")
    line.append("  ·  ", style=MUTED)
    if partial:
        line.append(f"{partial} partial", style=f"bold {WARN}")
        line.append("  ·  ", style=MUTED)
    line.append(f"{failed} fail", style=f"bold {ERR}")
    line.append("  ·  ", style=MUTED)
    line.append(f"{inconclusive} inconclusive", style=f"bold {WARN}")
    line.append(f"  ({total} total)", style=MUTED)
    line.append("\n")
    line.append("Evaluation ", style=MUTED)
    line.append(batch_id, style=ACCENT)
    line.append("\n", style="")
    line.append(
        "Bands  fail <50%  ·  partial 50–69%  ·  pass ≥70%  (suite-configurable)",
        style=MUTED,
    )
    out.print(Panel(line, border_style=ACCENT, padding=(0, 1)))
