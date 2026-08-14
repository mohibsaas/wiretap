"""Eval package public surface."""

from wiretap.eval.advisor import advise_for_run, advise_run
from wiretap.eval.judge import DEFAULT_FAIL_BELOW, DEFAULT_PASS_THRESHOLD, judge_call
from wiretap.eval.meta import check_caller_contract
from wiretap.eval.rules import run_rules
from wiretap.eval.tools import tool_report_text
from wiretap.eval.transcript import transcript_text

__all__ = [
    "DEFAULT_FAIL_BELOW",
    "DEFAULT_PASS_THRESHOLD",
    "advise_for_run",
    "advise_run",
    "check_caller_contract",
    "judge_call",
    "run_rules",
    "tool_report_text",
    "transcript_text",
]
