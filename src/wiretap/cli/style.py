"""Shared Rich styling helpers for wiretap CLI surfaces."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
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
    "scenario_progress",
    "spinner",
    "status_table",
    "step",
    "warn",
    "ScenarioGenProgress",
]
