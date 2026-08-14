"""Deterministic transcript rule checks."""

from __future__ import annotations

import re

from wiretap.eval.transcript import transcript_text
from wiretap.models import RuleCheck, RuleResult, TurnRecord


def run_rules(turns: list[TurnRecord], rules: RuleCheck) -> RuleResult:
    blob = transcript_text(turns).lower()
    # excludes are red lines for the agent under test. Matching the caller's own
    # words would fail an adversarial scenario for speaking its own bait.
    agent_blob = transcript_text([t for t in turns if t.role != "user"]).lower()
    failures: list[str] = []
    errors: list[str] = []
    for needle in rules.includes:
        if needle.lower() not in blob:
            failures.append(f"missing required phrase: {needle!r}")
    for needle in rules.excludes:
        if needle.lower() in agent_blob:
            failures.append(f"forbidden phrase present: {needle!r}")
    full = transcript_text(turns)
    for pattern in rules.patterns:
        try:
            matched = re.search(pattern, full, flags=re.IGNORECASE | re.MULTILINE)
        except re.error as exc:
            # An unparseable pattern is the suite author's bug. Raising here would
            # abort the run after the call was already spent, and recording it as
            # a rule failure would charge it to the agent.
            errors.append(f"invalid pattern {pattern!r}: {exc}")
            continue
        if not matched:
            failures.append(f"pattern not matched: {pattern!r}")
    return RuleResult(
        passed=not failures and not errors,
        failures=failures,
        errors=errors,
    )
