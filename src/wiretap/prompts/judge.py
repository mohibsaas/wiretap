"""LLM prompt for the call eval judge (LLM-as-judge).

Uses an analytic checklist + explicit pass gate so scores stay grounded in the
transcript rather than vibe.
"""

from __future__ import annotations


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
    rubric: str,
    transcript: str,
    tool_report: str = "",
) -> str:
    rubric_bit = (rubric or "").strip() or (
        "Pass only if success criteria are met from the transcript. "
        "Fail on invented facts, ignored clear intent, or policy breaks."
    )
    tool_block = _tool_evidence_block(tool_report)
    return f"""\
<role>
You are Wiretap's call evaluator. You score ONE completed voice-agent test call
using only the transcript, the recorded tool calls, and the supplied criteria.
You are not the caller and not the live agent.
</role>

<task>
Decide pass/fail against success criteria. When the call fails, give concrete
improvements for the live agent (not the test harness).
</task>

<success_criteria>
{success_criteria.strip() or "(none — use rubric only)"}
</success_criteria>

<rubric>
{rubric_bit}
</rubric>
{tool_block}
<scoring_guide>
Score is optional (number from 0.0 to 1.0) reflecting how fully criteria were met:
- 1.0: criteria clearly met; no material policy/factual failures
- 0.7–0.9: mostly met; minor gaps that do not break the call goal
- 0.4–0.6: partial; caller intent recognized but outcome incomplete or shaky
- 0.0–0.3: failed goal, harmful behavior, hallucination, or clear policy break
Set passed=true only when success criteria are substantially met (typically ≥ 0.7
unless the rubric defines a stricter bar). Prefer fail when uncertain.
A missing expected tool or a hallucinated completed action caps the score at 0.3
regardless of how competent the conversation sounded.
</scoring_guide>

<rules>
1. Ground every claim in the transcript or the tool evidence. Quote or paraphrase
   specific turns.
2. Do not invent tool results or account data. Treat tool behavior as evidence
   only when a <tool_evidence> section appears above.
3. Treat STT noise charitably: minor mishearings are not automatic fails unless
   the agent invents facts instead of clarifying.
4. Short voice turns are normal; do not fail solely for brevity.
5. If passed is true, suggestions MUST be [].
6. If passed is false, give 1–5 concrete, actionable suggestions for the live agent.
7. Never echo secrets, API keys, tokens, full credential strings, or tool
   argument values.
8. Respond with JSON only — no markdown fences, no preamble.
</rules>

<transcript>
{transcript}
</transcript>

<output_format>
{{
  "passed": false,
  "score": 0.0,
  "reason": "2–4 sentences citing transcript and, where present, tool evidence",
  "suggestions": ["concrete live-agent improvement", "..."]
}}
</output_format>
"""


__all__ = ["judge_call_prompt"]
