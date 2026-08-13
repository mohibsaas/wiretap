"""Validate the fake caller stayed on-contract (meta-eval)."""

from __future__ import annotations

from wiretap.models import Persona, TurnRecord


def check_caller_contract(
    *,
    persona: Persona,
    turns: list[TurnRecord],
    strict: bool = False,
) -> list[str]:
    """Return list of contract violations. Empty = OK."""
    violations: list[str] = []
    user_turns = [t for t in turns if t.role == "user"]
    if not user_turns:
        violations.append("caller produced no utterances")
        return violations

    known = {str(v).lower() for v in persona.knowledge.values() if v is not None}
    # In strict mode, forbid inventing long numeric IDs not in knowledge
    if strict:
        import re

        for t in user_turns:
            for match in re.findall(r"\b\d{6,}\b", t.text):
                if match.lower() not in known and not any(match in k for k in known):
                    violations.append(f"caller invented numeric id {match!r}")
                    break

    # Soft check: empty spam
    if all(len(t.text.strip()) < 2 for t in user_turns):
        violations.append("caller utterances too short / empty")

    return violations
