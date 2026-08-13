"""Central LLM / suite prompt library.

Edit prompts here — call sites import builders/constants, they do not
inline prompt text.

Agent briefs for generation live in ``wiretap.services.agent_brief`` (single
source — tools, end-call phrases, strong redaction).
"""

from wiretap.prompts.categories import (
    CATEGORY_CATALOG,
    DEFAULT_CATEGORIES,
    MAX_TESTS_PER_CATEGORY,
)
from wiretap.prompts.defaults import (
    DEFAULT_CALLER_OPENING,
    DEFAULT_GENERATED_RUBRIC,
    DEFAULT_PERSONA_PERSONALITY,
    DEFAULT_SUCCESS_CRITERIA,
    DO_NOT_REVEAL_TEST_BOT,
    FLOW_COVERAGE_OPENING,
    FLOW_COVERAGE_RUBRIC,
    IMPORTED_PERSONA_PERSONALITY,
    IMPORTED_SMOKE_RUBRIC,
)
from wiretap.prompts.judge import judge_call_prompt
from wiretap.prompts.suite_generation import (
    SUITE_GENERATION_SYSTEM,
    suite_generation_context,
    suite_generation_retry_user_message,
    suite_generation_user_message,
)
from wiretap.prompts.test_agent import (
    HANGUP_TOKEN,
    PHASE_DONE_TOKEN,
    TEST_AGENT_MAIN_TASK,
    TEST_AGENT_NEXT_REPLY,
    agent_said_message,
    caller_role_message,
    phase_task_message,
)

__all__ = [
    "CATEGORY_CATALOG",
    "DEFAULT_CALLER_OPENING",
    "DEFAULT_CATEGORIES",
    "DEFAULT_GENERATED_RUBRIC",
    "DEFAULT_PERSONA_PERSONALITY",
    "DEFAULT_SUCCESS_CRITERIA",
    "DO_NOT_REVEAL_TEST_BOT",
    "FLOW_COVERAGE_OPENING",
    "FLOW_COVERAGE_RUBRIC",
    "HANGUP_TOKEN",
    "IMPORTED_PERSONA_PERSONALITY",
    "IMPORTED_SMOKE_RUBRIC",
    "MAX_TESTS_PER_CATEGORY",
    "PHASE_DONE_TOKEN",
    "SUITE_GENERATION_SYSTEM",
    "TEST_AGENT_MAIN_TASK",
    "TEST_AGENT_NEXT_REPLY",
    "agent_said_message",
    "caller_role_message",
    "judge_call_prompt",
    "phase_task_message",
    "suite_generation_context",
    "suite_generation_retry_user_message",
    "suite_generation_user_message",
]
