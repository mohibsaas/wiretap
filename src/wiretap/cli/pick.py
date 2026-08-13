"""Interactive CLI pickers — skills.sh / Clack-style searchable ↑↓ menus.

Always drives the menu through ``/dev/tty`` when available so Rich's stdout
timeline and the raw menu don't fight over terminal modes. Falls back to a
typed prompt only when no controlling terminal exists.

Never logs secret values.
"""

from __future__ import annotations

import os
import select
import sys
from typing import Sequence, TextIO

import typer

from wiretap.cli import style as ui

try:
    import termios
    import tty
except ImportError:  # Windows — typed fallback only
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]

_CUSTOM = "__wiretap_custom__"
_CUSTOM_LABEL = "Type or paste custom…"
_MAX_VISIBLE = 10


def _tty_streams() -> tuple[TextIO, TextIO] | None:
    """Attach menu I/O to a real terminal.

    Prefer stdin/stdout when both are TTYs (normal ``wiretap init``).
    Fall back to ``/dev/tty`` when stdin is piped but a controlling tty exists.
    """
    if termios is None or tty is None:
        return None
    try:
        if sys.stdin.isatty() and sys.stdout.isatty():
            return sys.stdin, sys.stdout
    except Exception:
        pass
    try:
        tin = open("/dev/tty", "r", encoding="utf-8", errors="replace")
        tout = open("/dev/tty", "w", encoding="utf-8", errors="replace")
        return tin, tout
    except OSError:
        return None


def _close_tty_streams(streams: tuple[TextIO, TextIO]) -> None:
    for stream in streams:
        if stream not in (sys.stdin, sys.stdout):
            try:
                stream.close()
            except Exception:
                pass


def _drain_fd(fd: int) -> None:
    """Drop any buffered keypresses (e.g. leftover ``\\n`` after Enter)."""
    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                return
            if not os.read(fd, 1024):
                return
    except Exception:
        return


def _can_render_menu() -> bool:
    if termios is None or tty is None:
        return False
    if os.path.exists("/dev/tty"):
        return True
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


def _normalize_options(
    options: Sequence[str] | Sequence[tuple[str, str]],
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in options:
        if isinstance(item, tuple):
            label, value = str(item[0]), str(item[1])
        else:
            label = value = str(item)
        value = value.strip()
        label = label.strip() or value
        if not value or value in seen:
            continue
        seen.add(value)
        out.append((label, value))
    return out


def pick_option(
    label: str,
    options: Sequence[str] | Sequence[tuple[str, str]],
    *,
    default: str | None = None,
    allow_custom: bool = True,
    custom_prompt: str | None = None,
) -> str:
    """Show a searchable ↑↓ menu; optionally allow pasting a custom value."""
    pairs = _normalize_options(options)
    default = (default or "").strip() or (pairs[0][1] if pairs else "")

    if not pairs and allow_custom:
        return (
            typer.prompt(custom_prompt or label, default=default or "").strip() or default
        )
    if not pairs:
        return default

    streams = _tty_streams()
    if streams is not None:
        picked: str | None = None
        err: Exception | None = None
        try:
            try:
                ui.console.file.flush()
            except Exception:
                pass
            picked = _clack_pick(
                label,
                pairs,
                default=default,
                allow_custom=allow_custom,
                stdin=streams[0],
                stdout=streams[1],
            )
        except (KeyboardInterrupt, EOFError):
            raise typer.Exit(1) from None
        except Exception as exc:
            err = exc
            picked = None
        finally:
            _close_tty_streams(streams)

        if picked is not None:
            if picked == _CUSTOM:
                custom = typer.prompt(
                    custom_prompt or f"Paste custom {label.lower()}",
                    default=default if default not in {v for _, v in pairs} else "",
                ).strip()
                return custom or default
            return picked
        if err is not None:
            ui.warn(f"Menu unavailable ({type(err).__name__}) — type a value")

    return _fallback_pick(label, pairs, default=default, allow_custom=allow_custom)


def _clack_pick(
    label: str,
    pairs: list[tuple[str, str]],
    *,
    default: str,
    allow_custom: bool,
    stdin: TextIO,
    stdout: TextIO,
) -> str | None:
    """Searchable single-select on ``/dev/tty``, rail-aligned when in a timeline."""
    items: list[tuple[str, str]] = list(pairs)
    if allow_custom:
        items.append((_CUSTOM_LABEL, _CUSTOM))

    values = [v for _, v in items]
    cursor = values.index(default) if default in values else 0
    query = ""
    fd = stdin.fileno()
    old = termios.tcgetattr(fd)

    on_rail = ui.rail_active()
    green = ui.ansi_accent()
    dim = "\x1b[2m"
    bold = "\x1b[1m"
    reset = "\x1b[0m"
    prefix = f"{green}│{reset}  " if on_rail else "  "

    result: tuple[str, str] | None = None  # (label, value)

    def filtered() -> list[tuple[str, str]]:
        q = query.strip().lower()
        if not q:
            return items
        return [
            (disp, val)
            for disp, val in items
            if q in disp.lower() or q in val.lower()
        ]

    def write(s: str) -> None:
        stdout.write(s)
        stdout.flush()

    def paint(clear_rows: int) -> int:
        rows = filtered()
        if not rows:
            rows = [("(no matches — clear search)", "")]
            idx = 0
        else:
            idx = min(cursor, len(rows) - 1)

        if clear_rows > 0:
            write(f"\x1b[{clear_rows}A\r\x1b[J")

        lines: list[str] = []
        lines.append(f"{green}│{reset}" if on_rail else "")
        lines.append(f"{prefix}{bold}{label}{reset}")
        lines.append(f"{prefix}{dim}Search:{reset} {query}█")
        lines.append(
            f"{prefix}{dim}↑↓ move · type to filter · enter confirm · esc cancel{reset}"
        )
        lines.append(f"{green}│{reset}" if on_rail else "")

        n = len(rows)
        if n <= _MAX_VISIBLE:
            start, end = 0, n
        else:
            half = _MAX_VISIBLE // 2
            start = max(0, idx - half)
            end = min(n, start + _MAX_VISIBLE)
            start = max(0, end - _MAX_VISIBLE)

        if start > 0:
            lines.append(f"{prefix}{dim}↑ {start} more{reset}")

        for i in range(start, end):
            disp, val = rows[i]
            if not val:
                lines.append(f"{prefix}{dim}{disp}{reset}")
                continue
            if i == idx:
                # Soft cue: green pointer + accent text (no reverse / fill bar).
                lines.append(f"{prefix}{green}❯ {disp}{reset}")
            else:
                lines.append(f"{prefix}  {disp}")

        below = n - end
        if below > 0:
            lines.append(f"{prefix}{dim}↓ {below} more{reset}")

        lines.append(f"{green}│{reset}" if on_rail else "")
        # Skip leading empty line when not on rail so clear count stays accurate
        if not on_rail and lines and lines[0] == "":
            body = lines[1:]
            write("\n".join(body) + "\n")
            return len(body)
        write("\n".join(lines) + "\n")
        return len(lines)

    try:
        tty.setcbreak(fd)
        _drain_fd(fd)
        drawn = 0
        while True:
            rows = filtered()
            if rows and cursor >= len(rows):
                cursor = max(0, len(rows) - 1)
            drawn = paint(drawn)

            ch = stdin.read(1)
            if not ch:
                raise EOFError("tty closed")
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch == "\x1b":
                nxt = stdin.read(1)
                if nxt == "[":
                    code = stdin.read(1)
                    if code == "A":
                        cursor = max(0, cursor - 1)
                    elif code == "B":
                        cursor = min(max(0, len(rows) - 1), cursor + 1)
                    continue
                raise KeyboardInterrupt
            if ch in ("\r", "\n"):
                if not rows or not rows[cursor][1]:
                    continue
                result = rows[cursor]
                write(f"\x1b[{drawn}A\r\x1b[J")
                break
            if ch in ("\x7f", "\b"):
                query = query[:-1]
                cursor = 0
                continue
            if ord(ch) >= 32:
                query += ch
                cursor = 0
                continue
    finally:
        # Always restore before any Rich / Typer I/O.
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass
        _drain_fd(fd)

    if result is None:
        return None
    chosen_label, chosen = result
    # Rich is safe again — print confirmation on the timeline rail.
    # Close styles with `[/]` — `[/#hex]` does not match `[bold #hex]` (MarkupError).
    from rich.markup import escape

    ui.rail_text(
        f"[bold {ui.OK}]✓[/] {escape(label)}  "
        f"[bold {ui.ACCENT}]{escape(chosen_label)}[/]"
    )
    return chosen


def _fallback_pick(
    label: str,
    pairs: list[tuple[str, str]],
    *,
    default: str,
    allow_custom: bool,
) -> str:
    """Typed prompt when no interactive tty menu is available."""
    values = [v for _, v in pairs]
    if default not in values:
        default = values[0]
    shown = " · ".join(
        f"[bold {ui.ACCENT}]{disp}[/bold {ui.ACCENT}]"
        if val == default
        else f"[{ui.MUTED}]{disp}[/{ui.MUTED}]"
        for disp, val in pairs[:10]
    )
    ui.rail_text(
        f"[{ui.MUTED}]{label}:[/{ui.MUTED}] {shown}" + (" …" if len(pairs) > 10 else "")
    )
    if allow_custom:
        ui.rail_text(f"[{ui.MUTED}](or type / paste a custom id)[/{ui.MUTED}]")
    raw = typer.prompt(label, default=default).strip()
    if not raw:
        return default
    for disp, val in pairs:
        if raw == val or raw.lower() == disp.lower():
            return val
    if allow_custom:
        return raw
    ui.warn(f"Unknown {label} {raw!r} — using {default}")
    return default


__all__ = ["pick_option"]
