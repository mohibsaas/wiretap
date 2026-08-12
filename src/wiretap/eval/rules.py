"""Deterministic transcript rule checks."""

from __future__ import annotations

import re

from wiretap.eval.transcript import transcript_text
from wiretap.models import RuleCheck, RuleResult, TurnRecord


def run_rules(turns: list[TurnRecord], rules: RuleCheck) -> RuleResult:
    blob = transcript_text(turns).lower()
    failures: list[str] = []
    for needle in rules.includes:
        if needle.lower() not in blob:
            failures.append(f"missing required phrase: {needle!r}")
    for needle in rules.excludes:
        if needle.lower() in blob:
            failures.append(f"forbidden phrase present: {needle!r}")
    full = transcript_text(turns)
    for pattern in rules.patterns:
        if not re.search(pattern, full, flags=re.IGNORECASE | re.MULTILINE):
            failures.append(f"pattern not matched: {pattern!r}")
    return RuleResult(passed=not failures, failures=failures)
