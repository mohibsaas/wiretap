"""LLM prompt for goal-match call evaluation (LLM-as-judge).

Scores how well the live agent met the scenario success criteria / caller goal.
Wiretap maps the 0–1 score onto fail / partial / pass bands.
Optional tool evidence is included when the live platform recorded tool calls.
"""

from __future__ import annotations

import json


def _tool_evidence_block(tool_report: str) -> str:
    """Tool data plus its own rules, so <rules> numbering stays stable.

    Empty when tool use was not observable: a section that mentions tools while
    showing none would invite the judge to fail the agent for our blind spot.
    """
    report = (tool_report or "").strip()
    if not report:
        return ""
    return f"""
<tool_evidence>
The live agent's backend recorded these tool calls. If this section is absent,
tool use was not observable — judge the transcript alone and say nothing about
tools.

{report}

<tool_rules>
- An expected tool that never fired is a strong fail signal, but only when the
  transcript shows the call actually reached the point requiring it. A caller who
  abandoned early or never supplied required details is not a tool failure.
- A tool that returned an error, or whose arguments contradict what the caller
  said, is a failure even when the agent's spoken reply sounds correct.
- An agent that claims an action is done ("you're all booked") with no
  corresponding successful tool call has hallucinated the action — fail.
- Tools called beyond the expected list are not failures by themselves.
- Cite tools by name only. Never repeat argument values.
</tool_rules>
</tool_evidence>
"""


def judge_call_prompt(
    *,
    success_criteria: str,
    goal: str = "",
    scenario_name: str = "",
    rubric: str = "",
    transcript: str,
    fail_below: float = 0.5,
    pass_at: float = 0.7,
    tool_report: str = "",
) -> str:
    """Build the judge user prompt — single goal-match score, optional tools."""
    criteria = (success_criteria or "").strip() or "(none provided)"
    goal_bit = (goal or "").strip() or "(none — use success criteria)"
    name_bit = (scenario_name or "").strip() or "scenario"
    extra = (rubric or "").strip()
    extra_block = f"\n<extra_notes>\n{extra}\n</extra_notes>\n" if extra else ""
    tool_block = _tool_evidence_block(tool_report)

    return f"""\
<role>
You are Wiretap's call evaluator. You score ONE completed voice-agent test call
using the transcript, the supplied criteria, and (when present) recorded tool
calls. You are not the caller and not the live agent under test.
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
{extra_block}{tool_block}
<scoring_guide>
score = how completely the live agent achieved the success criteria / goal:
- 0.85–1.00: fully met; clear resolution aligned with the criteria
- 0.70–0.84: substantially met; minor gaps only
- 0.50–0.69: partial progress; important pieces missing
- 0.00–0.49: mostly failed, harmful, or criteria not addressed
When <tool_evidence> is present: a missing expected tool (after the call reached
the point requiring it) or a hallucinated completed action should keep the score
at or below 0.49.
Bands Wiretap will apply (do not invent other bands):
- score &lt; {fail_below:.2f} → fail
- {fail_below:.2f} ≤ score &lt; {pass_at:.2f} → partial
- score ≥ {pass_at:.2f} → pass
</scoring_guide>

<rules>
1. Ground the reason in the transcript and, when present, tool evidence. Cite or
   paraphrase specific turns.
2. Do not invent tool results, account data, or off-transcript events. Treat tool
   behavior as evidence only when a <tool_evidence> section appears above.
3. Treat STT noise charitably unless the agent invents facts instead of clarifying.
4. Score ONLY against caller_goal + success_criteria (and extra_notes / tools if
   present). Do not invent separate policy/empathy/flow rubrics.
5. If score ≥ {pass_at:.2f}, suggestions MUST be [].
6. Otherwise give 1–5 concrete, actionable suggestions for the live agent.
7. Never echo secrets, API keys, tokens, full credential strings, or tool
   argument values.
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
