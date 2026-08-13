"""Shared Rich styling helpers for wiretap CLI surfaces."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# Brand green (#13864E) — borders, headers, accents, success marks
ACCENT = "#13864E"
OK = "#13864E"
WARN = "yellow"
ERR = "red"
MUTED = "dim"

console = Console()


def banner(title: str, subtitle: str = "") -> None:
    """Hero-style command header."""
    head = Text()
    head.append("◈ ", style=f"bold {ACCENT}")
    head.append(title, style=f"bold {ACCENT}")
    if subtitle:
        head.append("\n")
        head.append(subtitle, style=MUTED)
    console.print(
        Panel(
            head,
            border_style=ACCENT,
            padding=(0, 1),
        )
    )


def step(num: int, total: int, title: str, *, detail: str = "") -> None:
    """Numbered step rule used by multi-stage wizards."""
    label = Text()
    label.append(f" {num}/{total} ", style=f"bold white on {ACCENT}")
    label.append(" ")
    label.append(title, style="bold")
    console.print()
    console.print(label)
    if detail:
        console.print(f"[{MUTED}]{detail}[/{MUTED}]")
    console.print(Rule(style=f"dim {ACCENT}"))


def ok(message: str) -> None:
    console.print(f"[bold {OK}]✓[/bold {OK}] {message}")


def warn(message: str) -> None:
    console.print(f"[bold {WARN}]![/bold {WARN}] [{WARN}]{message}[/{WARN}]")


def err(message: str) -> None:
    console.print(f"[bold {ERR}]✗[/bold {ERR}] [{ERR}]{message}[/{ERR}]")


def info(message: str) -> None:
    console.print(f"[{ACCENT}]→[/{ACCENT}] {message}")


def muted(message: str) -> None:
    console.print(f"[{MUTED}]{message}[/{MUTED}]")


@contextmanager
def spinner(message: str) -> Iterator[None]:
    """Animated loader for long-running steps (LLM generate, import, …)."""
    with console.status(
        f"[{ACCENT}]{message}[/{ACCENT}]",
        spinner="dots",
        spinner_style=ACCENT,
    ):
        yield


@dataclass
class ScenarioGenProgress:
    """Live ``done/total`` progress while LLM suite generation runs."""

    total: int
    _progress: Progress = field(init=False, repr=False)
    _task_id: int | None = field(default=None, repr=False)
    _finished: list[str] = field(default_factory=list, repr=False)
    titles: list[tuple[str, str]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._progress = Progress(
            SpinnerColumn(style=ACCENT),
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=24, style=ACCENT, complete_style=ACCENT),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )

    def __enter__(self) -> ScenarioGenProgress:
        self._progress.start()
        self._task_id = self._progress.add_task(
            "Generating scenarios",
            total=max(1, self.total),
        )
        return self

    def __exit__(self, *exc: object) -> None:
        if self._task_id is not None:
            self._progress.update(self._task_id, completed=self.total)
        self._progress.stop()

    def __call__(self, event: dict[str, Any]) -> None:
        """Progress callback compatible with ``generate_suite(on_progress=…)``."""
        if self._task_id is None:
            return
        kind = event.get("kind")
        done = int(event.get("done") or 0)
        total = int(event.get("total") or self.total or 1)
        category = str(event.get("category") or "")
        batch = int(event.get("batch") or 0)

        if kind == "start":
            self.total = total
            self._progress.update(
                self._task_id,
                total=max(1, total),
                completed=0,
                description="Generating scenarios",
            )
            return

        if kind == "category_start":
            label = f"Generating [{category}] (+{batch})"
            if self._finished:
                label = f"{', '.join(self._finished)} ✓ · {label}"
            self._progress.update(
                self._task_id,
                completed=done,
                total=max(1, total),
                description=label,
            )
            return

        if kind == "category_done":
            if category and category not in self._finished:
                self._finished.append(category)
            titles = [str(t).strip() for t in (event.get("titles") or []) if str(t).strip()]
            for title in titles:
                self.titles.append((category, title))
                # Print under the live bar so titles accumulate as a readable list.
                self._progress.console.print(
                    f"  [{ACCENT}]•[/{ACCENT}] [{MUTED}]{category}[/{MUTED}]  {title}"
                )
            label = f"Generated {done}/{total}"
            if category:
                label += f" · {category} ✓"
            self._progress.update(
                self._task_id,
                completed=done,
                total=max(1, total),
                description=label,
            )
            return

        if kind == "done":
            self._progress.update(
                self._task_id,
                completed=done or total,
                total=max(1, total),
                description=f"Generated {done or total}/{total} scenarios",
            )


@contextmanager
def scenario_progress(total: int) -> Iterator[ScenarioGenProgress]:
    """Context manager yielding a live generation progress callback."""
    with ScenarioGenProgress(total=max(1, total)) as prog:
        yield prog


def print_suite_view(
    suite: Any,
    *,
    name: str = "",
    path: str | None = None,
    detail: bool = False,
    scenario: str | None = None,
) -> None:
    """Pretty-print a suite: header + scenario table, or detailed cards."""
    agent = getattr(suite, "agent", None)
    models = getattr(suite, "models", None)
    speech = getattr(suite, "speech", None)
    scenarios = list(getattr(suite, "scenarios", None) or [])
    personas = {p.id: p for p in (getattr(suite, "personas", None) or [])}

    title = name or getattr(agent, "agent_id", None) or "suite"
    head = Text()
    head.append("◈ ", style=f"bold {ACCENT}")
    head.append(str(title), style=f"bold {ACCENT}")
    if path:
        head.append("\n")
        head.append(str(path), style=MUTED)

    meta = Text()
    plat = getattr(agent, "platform", None) or "custom"
    transport = getattr(getattr(agent, "transport", None), "value", None) or getattr(
        agent, "transport", "—"
    )
    agent_id = getattr(agent, "agent_id", None) or "—"
    meta.append("Platform ", style=MUTED)
    meta.append(str(plat), style=f"bold {ACCENT}")
    meta.append("  ·  Agent ", style=MUTED)
    meta.append(str(agent_id), style=ACCENT)
    meta.append("  ·  Transport ", style=MUTED)
    meta.append(str(transport), style=ACCENT)

    console.print(Panel(Group(head, Text(), meta), border_style=ACCENT, padding=(0, 1)))

    detail_meta = Table(show_header=False, box=None, pad_edge=False, padding=(0, 2))
    detail_meta.add_column(style=MUTED)
    detail_meta.add_column()
    if models:
        detail_meta.add_row(
            "Models",
            f"[{ACCENT}]{getattr(models, 'simulator', '—')}[/{ACCENT}] sim  ·  "
            f"[{ACCENT}]{getattr(models, 'judge', '—')}[/{ACCENT}] judge",
        )
    if speech:
        detail_meta.add_row(
            "Speech",
            f"[{ACCENT}]{getattr(speech, 'stt', '—')}[/{ACCENT}] STT  ·  "
            f"[{ACCENT}]{getattr(speech, 'tts', '—')}[/{ACCENT}] TTS  ·  "
            f"[{ACCENT}]{getattr(speech, 'voice', '—')}[/{ACCENT}] voice",
        )
    detail_meta.add_row("Scenarios", f"[bold]{len(scenarios)}[/bold]")
    console.print(detail_meta)
    console.print()

    indexed = list(enumerate(scenarios, start=1))
    if scenario:
        selected = _match_scenarios(indexed, scenario)
        if not selected:
            err(f"No scenario matched {scenario!r}")
            muted("Use a number (#), scenario id, or title substring.")
            return
        indexed = selected

    if detail or scenario:
        for i, sc in indexed:
            print_scenario_detail(
                sc,
                index=i,
                persona=personas.get(getattr(sc, "persona_id", "")),
            )
        return

    table = Table(
        title=Text("Scenarios", style=f"bold {ACCENT}"),
        show_header=True,
        header_style=f"bold {ACCENT}",
        border_style=ACCENT,
        pad_edge=True,
        expand=True,
    )
    table.add_column("#", style=MUTED, width=4, justify="right")
    table.add_column("Category", style=ACCENT, min_width=12)
    table.add_column("Title", style="bold", ratio=2, overflow="fold")
    table.add_column("Opening", style=MUTED, ratio=2, overflow="fold")

    for i, sc in indexed:
        opening = ""
        beats = getattr(sc, "beats", None) or []
        if beats:
            opening = str(getattr(beats[0], "say", "") or "").strip()
        if len(opening) > 72:
            opening = opening[:69].rstrip() + "…"
        table.add_row(
            str(i),
            str(getattr(sc, "category", None) or "—"),
            str(getattr(sc, "name", None) or getattr(sc, "id", "")),
            opening or "—",
        )
    console.print(table)
    muted("Tip: wiretap suite show <name> --detail   or   --detail -t 3")


def print_scenario_detail(
    scenario: Any,
    *,
    index: int,
    persona: Any | None = None,
) -> None:
    """Pretty-print one scenario with full eval fields."""
    title = str(getattr(scenario, "name", None) or getattr(scenario, "id", "") or "scenario")
    category = str(getattr(scenario, "category", None) or "—")
    sid = str(getattr(scenario, "id", "") or "")

    head = Text()
    head.append(f" #{index} ", style=f"bold white on {ACCENT}")
    head.append(" ")
    head.append(title, style="bold")
    head.append(f"  [{category}]", style=MUTED)
    if sid:
        head.append(f"\nid  {sid}", style=MUTED)

    rows = Table(show_header=False, box=None, pad_edge=False, padding=(0, 1))
    rows.add_column(style=MUTED, min_width=14)
    rows.add_column(overflow="fold")

    if persona is not None:
        rows.add_row(
            "Persona",
            str(getattr(persona, "name", None) or getattr(persona, "id", "") or "—"),
        )
        rows.add_row("Identity", str(getattr(persona, "identity", "") or "—"))
        rows.add_row("Goal", str(getattr(persona, "goal", "") or "—"))
        personality = str(getattr(persona, "personality", "") or "").strip()
        if personality:
            rows.add_row("Personality", personality)
        constraints = list(getattr(persona, "constraints", None) or [])
        if constraints:
            rows.add_row("Constraints", " · ".join(str(c) for c in constraints))

    rows.add_row("Max turns", str(getattr(scenario, "max_turns", "—")))
    rows.add_row(
        "Success",
        str(getattr(scenario, "success_criteria", "") or "—"),
    )
    rubric = str(getattr(scenario, "rubric", "") or "").strip()
    if rubric:
        rows.add_row("Rubric", rubric)

    rules = getattr(scenario, "rules", None)
    if rules is not None:
        excludes = list(getattr(rules, "excludes", None) or [])
        includes = list(getattr(rules, "includes", None) or [])
        patterns = list(getattr(rules, "patterns", None) or [])
        if excludes:
            rows.add_row("Excludes", " · ".join(str(x) for x in excludes))
        if includes:
            rows.add_row("Includes", " · ".join(str(x) for x in includes))
        if patterns:
            rows.add_row("Patterns", " · ".join(str(x) for x in patterns))

    beats = list(getattr(scenario, "beats", None) or [])
    if beats:
        beat_lines = []
        for b in beats:
            at = getattr(b, "at_turn", "?")
            say = str(getattr(b, "say", "") or "").strip()
            beat_lines.append(f"turn {at}: {say}")
        rows.add_row("Beats", "\n".join(beat_lines))

    phases = list(getattr(scenario, "flow_phases", None) or [])
    if phases:
        phase_lines = []
        for p in phases:
            if isinstance(p, dict):
                pid = p.get("id") or p.get("name") or "phase"
                task = p.get("task") or p.get("name") or ""
                phase_lines.append(f"{pid}: {task}")
            else:
                phase_lines.append(str(p))
        rows.add_row("Phases", "\n".join(phase_lines))

    console.print(Panel(Group(head, Text(), rows), border_style=ACCENT, padding=(0, 1)))
    console.print()


def _match_scenarios(
    indexed: list[tuple[int, Any]],
    query: str,
) -> list[tuple[int, Any]]:
    """Match by 1-based index, exact id, or case-insensitive title/id substring."""
    q = (query or "").strip()
    if not q:
        return indexed
    if q.isdigit():
        n = int(q)
        return [(i, sc) for i, sc in indexed if i == n]
    q_lower = q.lower()
    exact = [
        (i, sc)
        for i, sc in indexed
        if str(getattr(sc, "id", "")).lower() == q_lower
        or str(getattr(sc, "name", "")).lower() == q_lower
    ]
    if exact:
        return exact
    return [
        (i, sc)
        for i, sc in indexed
        if q_lower in str(getattr(sc, "id", "")).lower()
        or q_lower in str(getattr(sc, "name", "")).lower()
    ]


def next_cmd(command: str, *, hint: str = "Next") -> None:
    console.print()
    console.print(f"[{MUTED}]{hint}:[/{MUTED}] [bold {ACCENT}]{command}[/bold {ACCENT}]")


def platform_table(platforms: list[str], *, default: str = "retell") -> None:
    """Colored platform chooser reference."""
    table = Table(
        show_header=True,
        header_style=f"bold {ACCENT}",
        border_style="dim",
        box=None,
        pad_edge=False,
    )
    table.add_column("#", style=MUTED, width=3)
    table.add_column("Platform", style=f"bold {ACCENT}")
    table.add_column("Notes", style=MUTED)
    notes = {
        "retell": "LiveKit web-call",
        "vapi": "WebSocket PCM",
        "elevenlabs": "ConvAI signed URL",
        "livekit": "Join room + JWT",
        "synthflow": "WS media (needs numbers)",
        "bolna": "Import now · live dial later",
        "custom": "Stub / text only",
    }
    for i, p in enumerate(platforms, start=1):
        name = Text(p)
        if p == default:
            name.append("  (default)", style=MUTED)
        table.add_row(str(i), name, notes.get(p, ""))
    console.print(table)


def status_table(
    *,
    rows: list[tuple[str, str | Text]],
    title: str = "wiretap status",
) -> None:
    table = Table(
        title=Text(title, style=f"bold {ACCENT}"),
        show_header=True,
        header_style=f"bold {ACCENT}",
        border_style=ACCENT,
        pad_edge=True,
    )
    table.add_column("Item", style="bold", min_width=14)
    table.add_column("Value")
    for item, value in rows:
        table.add_row(item, value)
    console.print(table)


__all__ = [
    "ACCENT",
    "ERR",
    "MUTED",
    "OK",
    "WARN",
    "banner",
    "console",
    "err",
    "info",
    "muted",
    "next_cmd",
    "ok",
    "platform_table",
    "print_scenario_detail",
    "print_suite_view",
    "scenario_progress",
    "spinner",
    "status_table",
    "step",
    "warn",
    "ScenarioGenProgress",
]
