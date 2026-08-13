"""Helpers to commit complete agent utterances (not streaming prefixes)."""

from __future__ import annotations

# Trailing words that usually mean the speaker has not finished the clause.
_CONNECTOR_ENDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "be",
        "because",
        "but",
        "by",
        "for",
        "from",
        "if",
        "in",
        "into",
        "is",
        "of",
        "on",
        "or",
        "so",
        "than",
        "that",
        "the",
        "to",
        "with",
        "i'll",
        "we'll",
        "you'll",
        "they'll",
        "i'm",
        "we're",
        "you're",
        "they're",
        "i've",
        "we've",
        "you've",
        "they've",
        "gonna",
        "wanna",
        "make",
        "get",
        "let",
        "just",
        "really",
        "very",
        "how",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
    }
)


def normalize_agent_text(text: str | None) -> str:
    return (text or "").strip()


def looks_incomplete_utterance(text: str | None) -> bool:
    """True when STT text likely ends mid-clause (any batch STT provider).

    Conservative on purpose: returning True for *every* non-punctuated line
    doubles STT + silence wait and blows the scenario timeout. Only hold back
    when the ending is a strong mid-clause signal.
    """
    t = normalize_agent_text(text)
    if not t:
        return True
    if t[-1] in ".?!…":
        return False
    if len(t) >= 2 and t[-1] in "\"'" and t[-2] in ".?!":
        return False
    core = t.rstrip("\"'")
    if core and core[-1] in ",:;—":
        return True
    words = core.lower().replace("—", " ").replace("-", " ").split()
    if not words:
        return True
    last = words[-1].strip(".,;:!?\"'")
    if last in _CONNECTOR_ENDS:
        return True
    # Very short fragment with no terminal punct → almost certainly cut early.
    if len(words) <= 5:
        return True
    # Longer speech without punctuation is common from batch STT; commit it.
    return False


def accept_final_utterance(text: str, seen: set[str]) -> str | None:
    """Return text to enqueue once, preferring longer finals over prefixes.

    Returns None if ``text`` is empty, already seen, or a shorter prefix of a
    previously accepted utterance.
    """
    text = normalize_agent_text(text)
    if not text or text in seen:
        return None
    # Drop shorter prefixes so a later longer final can be accepted.
    shorter = {s for s in seen if text.startswith(s) and text != s}
    seen -= shorter
    if any(prev.startswith(text) and prev != text for prev in seen):
        return None
    seen.add(text)
    return text


def merge_growing_text(prev: str, new: str) -> str:
    """Merge interim ASR / sliding-window fragments into one draft string.

    Retell ``update.transcript`` only keeps the last ~5 sentences; a later
    update may replace a long growing line with a trailing fragment. Prefer
    growth, keep the longer prefix, or stitch on overlap instead of treating
    every non-prefix change as a brand-new utterance.
    """
    prev = normalize_agent_text(prev)
    new = normalize_agent_text(new)
    if not prev:
        return new
    if not new:
        return prev
    if new == prev or new.startswith(prev):
        return new
    if prev.startswith(new):
        return prev
    if new in prev:
        return prev
    if prev in new:
        return new

    # Longest overlap where the end of ``prev`` matches the start of ``new``.
    max_k = min(len(prev), len(new))
    for k in range(max_k, 0, -1):
        if prev.endswith(new[:k]):
            return prev + new[k:]
    return new


def is_distinct_utterance(prev: str, new: str) -> bool:
    """True when ``new`` looks like a separate utterance, not a revision of ``prev``."""
    prev = normalize_agent_text(prev)
    new = normalize_agent_text(new)
    if not prev or not new or prev == new:
        return False
    if new.startswith(prev) or prev.startswith(new):
        return False
    if new in prev or prev in new:
        return False
    merged = merge_growing_text(prev, new)
    # Overlap stitch produced a longer combined string → same utterance.
    if merged != new and (merged.startswith(prev) or prev in merged):
        return False
    # Shared wordy overlap (≥12 chars) ⇒ revision, not a new turn.
    max_k = min(len(prev), len(new), 80)
    for k in range(max_k, 11, -1):
        if prev.endswith(new[:k]) or new.endswith(prev[:k]):
            return False
    return True


def coalesce_utterances(parts: list[str]) -> str:
    """Join successive committed fragments from one agent turn into one string."""
    out = ""
    for part in parts:
        part = normalize_agent_text(part)
        if not part:
            continue
        if not out:
            out = part
            continue
        if not is_distinct_utterance(out, part):
            out = merge_growing_text(out, part)
        else:
            sep = " "
            out = f"{out.rstrip()}{sep}{part.lstrip()}"
    return normalize_agent_text(out)


def transcript_fragment_score(turns: list) -> float:
    """0–1 score of how chopped a transcript looks (higher = worse).

    Used to pick live vs provider_final for judging — provider-agnostic.
    """
    if not turns:
        return 1.0
    short = 0
    for t in turns:
        text = normalize_agent_text(getattr(t, "text", None) or "")
        words = text.split()
        if len(words) <= 3:
            short += 1
            continue
        if text and text[-1] not in ".?!…\"'" and len(words) <= 6:
            short += 1
    return short / max(1, len(turns))


def pick_judge_transcript(
    live: list,
    official: list | None,
) -> tuple[list, str]:
    """Choose the cleaner transcript for LLM judge / rules.

    Prefer provider final when it is at least as coherent as live; otherwise
    keep live (avoids scoring barge-in shredded provider windows).
    """
    if not official:
        return live, "live"
    live_users = sum(1 for t in live if getattr(t, "role", None) == "user")
    off_users = sum(1 for t in official if getattr(t, "role", None) == "user")
    # Provider never heard the caller — live is the only usable dialogue.
    if live_users and not off_users:
        return live, "live_provider_missed_user"
    live_score = transcript_fragment_score(live)
    off_score = transcript_fragment_score(official)
    if off_score > live_score + 0.12 and live_users > 0:
        return live, "live_less_fragmented"
    return official, "provider_final"


def is_vapi_final_transcript(data: dict) -> bool:
    """Vapi sends partial + final assistant transcripts; only finals are turns."""
    t = str(data.get("transcriptType") or data.get("transcript_type") or "final").lower()
    return t in {"final", "end", ""}


def _as_ms(value: object) -> float | None:
    """Coerce provider clocks to milliseconds (accepts seconds or ms)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if not (n >= 0) or n != n:  # NaN
        return None
    # Heuristic: values under 1e5 are almost certainly seconds for call audio.
    if n < 100_000:
        return n * 1000.0
    return n


def utterance_timing_ms(utt: dict) -> tuple[float | None, float | None]:
    """Extract (start_ms, end_ms) from a provider utterance dict.

    Prefers word-level ``words[].start`` / ``end`` (Retell-style, seconds).
    Falls back to utterance-level start/end fields when present.
    """
    starts: list[float] = []
    ends: list[float] = []
    words = utt.get("words")
    if isinstance(words, list):
        for w in words:
            if not isinstance(w, dict):
                continue
            s = _as_ms(w.get("start"))
            e = _as_ms(w.get("end"))
            if s is not None:
                starts.append(s)
            if e is not None:
                ends.append(e)
            elif s is not None:
                ends.append(s)

    if starts and ends:
        start_ms = min(starts)
        end_ms = max(ends)
        if end_ms < start_ms:
            end_ms = start_ms
        return start_ms, end_ms

    for sk, ek in (
        ("start", "end"),
        ("start_ms", "end_ms"),
        ("startSec", "endSec"),
        ("start_sec", "end_sec"),
    ):
        s = _as_ms(utt.get(sk))
        e = _as_ms(utt.get(ek))
        if s is not None and e is not None:
            if e < s:
                e = s
            return s, e
    return None, None
