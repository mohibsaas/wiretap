"""LLM prompt for goal-match call evaluation (LLM-as-judge).

Scores how well the live agent met the scenario success criteria / caller goal.
Wiretap maps the 0–1 score onto fail / partial / pass bands.
"""

from __future__ import annotations

import json


def judge_call_prompt(
    *,
    success_criteria: str,
    goal: str = "",
    scenario_name: str = "",
    rubric: str = "",
    transcript: str,
    fail_below: float = 0.5,
    pass_at: float = 0.7,
) -> str:
    """Build the judge user prompt — single goal-match score, no multi-rubric pack."""
    criteria = (success_criteria or "").strip() or "(none provided)"
    goal_bit = (goal or "").strip() or "(none — use success criteria)"
    name_bit = (scenario_name or "").strip() or "scenario"
    extra = (rubric or "").strip()
    extra_block = f"\n<extra_notes>\n{extra}\n</extra_notes>\n" if extra else ""

    return f"""\
<role>
You are Wiretap's call evaluator. You score ONE completed voice-agent test call.
You are not the caller and not the live agent under test.
</role>

<task>
Judge how well the LIVE AGENT satisfied the caller's goal and this scenario's
success criteria. Return a single match score from 0.0–1.0 (Wiretap shows it as
a percentage and maps it to fail / partial / pass).
</task>

<scenario>
{name_bit}
</scenario>

<caller_goal>
{goal_bit}
</caller_goal>

<success_criteria>
{criteria}
</success_criteria>
{extra_block}
<scoring_guide>
score = how completely the live agent achieved the success criteria / goal:
- 0.85–1.00: fully met; clear resolution aligned with the criteria
- 0.70–0.84: substantially met; minor gaps only
- 0.50–0.69: partial progress; important pieces missing
- 0.00–0.49: mostly failed, harmful, or criteria not addressed
Bands Wiretap will apply (do not invent other bands):
- score &lt; {fail_below:.2f} → fail
- {fail_below:.2f} ≤ score &lt; {pass_at:.2f} → partial
- score ≥ {pass_at:.2f} → pass
</scoring_guide>

<rules>
1. Ground the reason in the transcript. Cite or paraphrase specific turns.
2. Do not invent tool results, account data, or off-transcript events.
3. Treat STT noise charitably unless the agent invents facts instead of clarifying.
4. Score ONLY against caller_goal + success_criteria (and extra_notes if present).
   Do not invent separate policy/empathy/flow rubrics.
5. If score ≥ {pass_at:.2f}, suggestions MUST be [].
6. Otherwise give 1–5 concrete, actionable suggestions for the live agent.
7. Never echo secrets, API keys, tokens, or full credential strings.
8. Respond with JSON only — no markdown fences, no preamble.
</rules>

<transcript>
{transcript}
</transcript>

<output_format>
{json.dumps({
    "score": 0.0,
    "reason": "2–4 sentences: how the call matched (or missed) the goal / success criteria",
    "suggestions": ["concrete live-agent improvement", "..."],
}, indent=2)}
</output_format>
"""


__all__ = ["judge_call_prompt"]
