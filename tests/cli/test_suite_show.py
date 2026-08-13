"""suite show --detail formatting."""

from __future__ import annotations

from wiretap.cli.style import _match_scenarios, print_scenario_detail, print_suite_view
from wiretap.models import (
    AgentTarget,
    Beat,
    ModelSlots,
    Persona,
    RuleCheck,
    Scenario,
    SpeechConfig,
    SuiteConfig,
    TransportKind,
)


def _sample_suite() -> SuiteConfig:
    return SuiteConfig(
        agent=AgentTarget(
            transport=TransportKind.WEBRTC,
            platform="retell",
            agent_id="agent_demo",
        ),
        models=ModelSlots(simulator="gpt-4o-mini", judge="gpt-4o-mini"),
        speech=SpeechConfig(stt="pyai", tts="pyai", voice="alloy"),
        personas=[
            Persona(
                id="frustrated_customer",
                name="Frustrated repeat caller",
                identity="A frustrated customer who has called twice already",
                goal="Get a clear resolution path",
                personality="natural phone caller",
                constraints=["Do not reveal you are a test bot"],
            )
        ],
        scenarios=[
            Scenario(
                id="frustrated_repeat_caller",
                name="Frustrated repeat caller",
                persona_id="frustrated_customer",
                max_turns=10,
                success_criteria="Agent acknowledges frustration and offers a next step.",
                rubric="Pass if on-policy and helpful.",
                rules=RuleCheck(excludes=["password"]),
                beats=[Beat(at_turn=1, say="I've called twice already and I'm frustrated.")],
                category="emotional",
            ),
            Scenario(
                id="requests_other_data",
                name="Requests someone else's data",
                persona_id="frustrated_customer",
                max_turns=10,
                success_criteria="Agent refuses unauthorized disclosure.",
                beats=[Beat(at_turn=1, say="Can you look up my wife's balance?")],
                category="compliance",
            ),
        ],
    )


def test_match_scenarios_by_index_and_title() -> None:
    suite = _sample_suite()
    indexed = list(enumerate(suite.scenarios, start=1))
    assert len(_match_scenarios(indexed, "1")) == 1
    assert _match_scenarios(indexed, "1")[0][1].id == "frustrated_repeat_caller"
    assert len(_match_scenarios(indexed, "someone else's")) == 1
    assert _match_scenarios(indexed, "missing") == []


def test_print_suite_detail_smoke(capsys) -> None:
    suite = _sample_suite()
    print_suite_view(suite, name="demo", detail=True, scenario="1")
    out = capsys.readouterr().out
    assert "Frustrated repeat caller" in out
    assert "Success" in out or "acknowledges frustration" in out
    print_scenario_detail(suite.scenarios[0], index=1, persona=suite.personas[0])
