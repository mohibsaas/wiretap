"""Generation with an agent brief: payload grounding + stop-word guard."""

from __future__ import annotations

import json
from typing import Any

import pytest

from wiretap.services.generator import generate_suite, llm_generate_category_tests

BRIEF: dict[str, Any] = {
    "agent_name": "Clinic bot",
    "summary": "Role: book cleanings and quote the published fee.",
    "tools": [{"name": "book_appointment", "description": "Books a slot"}],
    "irreversible_tools": ["book_appointment"],
    "flow_nodes": [{"id": "verify_patient", "type": "conversation"}],
    "language": "en",
    "end_call_phrases": ["goodbye now", "have a nice day"],
    "prompt_excerpt": "You are a clinic booking agent.",
}


def _test_case(name: str, say: str) -> dict[str, Any]:
    return {
        "name": name,
        "identity": f"Caller {name}",
        "goal": f"Goal {name}",
        "say": say,
        "success": f"Success {name}",
        "excludes": [],
    }


class _Recorder:
    """Stand-in for providers.llm.complete that records every call."""

    def __init__(self, responses: list[list[dict[str, Any]]]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        return json.dumps(self._responses[index])

    @property
    def payloads(self) -> list[str]:
        return [
            msg["content"]
            for call in self.calls
            for msg in call["messages"]
            if msg["role"] == "user"
        ]

    @property
    def systems(self) -> list[str]:
        return [
            msg["content"]
            for call in self.calls
            for msg in call["messages"]
            if msg["role"] == "system"
        ]


def test_brief_reaches_the_generation_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _Recorder([[_test_case("A", "Hi, I need to book a cleaning.")]])
    monkeypatch.setattr("wiretap.services.generator.complete", fake)

    llm_generate_category_tests(
        category="task", count=1, agent_name="Clinic bot", brief=BRIEF
    )

    payload = fake.payloads[0]
    assert "agent_brief" in payload
    assert "book_appointment" in payload
    assert "verify_patient" in payload
    assert "book cleanings" in payload

    system = fake.systems[0]
    assert "ground every scenario in it" in system
    assert "end_call_phrases" in system


def test_no_brief_says_so_instead_of_sending_a_partial_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _Recorder([[_test_case("A", "Hi, I need help today.")]])
    monkeypatch.setattr("wiretap.services.generator.complete", fake)

    llm_generate_category_tests(category="task", count=1, agent_name="Bot")

    payload = fake.payloads[0]
    brief_block = payload.split("<agent_brief>")[1].split("</agent_brief>")[0]
    assert "not provided" in brief_block
    assert "{" not in brief_block


def test_stop_word_opening_is_rejected_and_re_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _Recorder(
        [
            # First pass: one usable line, one that would hang up the call.
            [
                _test_case("Good", "Hi, I need to book a cleaning."),
                _test_case("Hangs up", "Goodbye now, that's all I needed."),
            ],
            [_test_case("Replacement", "Hello, can I move my appointment?")],
        ]
    )
    monkeypatch.setattr("wiretap.services.generator.complete", fake)

    out = llm_generate_category_tests(
        category="task", count=2, agent_name="Clinic bot", brief=BRIEF
    )

    assert len(fake.calls) == 2, "rejection should trigger the shortfall retry"
    names = [t["name"] for t in out]
    assert names == ["Good", "Replacement"]
    assert all("goodbye now" not in t["say"].lower() for t in out)


def test_bare_farewell_rejected_without_a_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _Recorder(
        [
            [_test_case("Bye", "Bye, thanks anyway.")],
            [_test_case("Fixed", "Hi, I have a question about my bill.")],
        ]
    )
    monkeypatch.setattr("wiretap.services.generator.complete", fake)

    out = llm_generate_category_tests(category="task", count=1, agent_name="Bot")

    assert [t["name"] for t in out] == ["Fixed"]


def test_purpose_suffixes_dropped_when_brief_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _Recorder([[_test_case("A", "Hi, I need to book a cleaning.")]])
    monkeypatch.setattr("wiretap.services.generator.complete", fake)

    suite = generate_suite(
        platform="retell",
        agent_id="agent_1",
        agent_name="Clinic bot",
        purpose="dental booking",
        categories=["task"],
        tests_per_category=1,
        brief=BRIEF,
    )

    assert "Context: dental booking" not in suite.personas[0].goal
    assert "Align with purpose" not in suite.scenarios[0].success_criteria


def test_purpose_suffixes_kept_without_a_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    """Purpose-only suites still lean on the suffixes for grounding."""
    fake = _Recorder([[_test_case("A", "Hi, I need help today.")]])
    monkeypatch.setattr("wiretap.services.generator.complete", fake)

    suite = generate_suite(
        platform="custom",
        agent_id=None,
        agent_name="Bot",
        purpose="dental booking",
        categories=["task"],
        tests_per_category=1,
    )

    assert "Context: dental booking" in suite.personas[0].goal
    assert "Align with purpose: dental booking" in suite.scenarios[0].success_criteria
