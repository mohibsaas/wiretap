"""Choosing web or phone at run time, and finding the number to dial.

Phone is a per-run decision rather than a suite property, so these cover the
three ways it gets made: an explicit flag, a remembered pick, and a prompt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from wiretap.cli import prompts
from wiretap.cli.main import app
from wiretap.models import (
    AgentTarget,
    Persona,
    Scenario,
    SuiteConfig,
    TransportKind,
)
from wiretap.services.agent_numbers import AgentNumber, saved_agent_number
from wiretap.suite.loader import dump_suite

AGENT = "agent_abc"


def _suite(
    *,
    transport: TransportKind = TransportKind.WEBRTC,
    phone_number: str | None = None,
    scenarios: int = 1,
) -> SuiteConfig:
    return SuiteConfig(
        agent=AgentTarget(
            transport=transport,
            platform="retell",
            agent_id=AGENT,
            phone_number=phone_number,
            token_env="RETELL_API_KEY",
        ),
        personas=[Persona(id="caller", name="Caller", identity="A caller", goal="Help")],
        scenarios=[
            Scenario(
                id=f"case_{i}",
                name=f"Case {i}",
                persona_id="caller",
                success_criteria="ok",
            )
            for i in range(scenarios)
        ],
    )


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WIRETAP_HOME", str(tmp_path))


@pytest.fixture()
def interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompts, "is_interactive", lambda: True)


def _answer(monkeypatch: pytest.MonkeyPatch, *replies: str) -> list[str]:
    """Feed canned prompt replies and record the labels that were asked."""
    asked: list[str] = []
    queue = list(replies)

    def fake_prompt(label: str, *args: Any, **kwargs: Any) -> str:
        asked.append(label)
        return queue.pop(0) if queue else str(kwargs.get("default", ""))

    monkeypatch.setattr(typer, "prompt", fake_prompt)
    return asked


# --- choosing the transport -------------------------------------------------


@pytest.mark.parametrize("word", ["phone", "pstn", "PHONE", "call"])
def test_the_flag_can_ask_for_a_real_call(word: str) -> None:
    assert prompts.choose_transport(_suite(), transport=word) == "pstn"


def test_asking_for_web_on_a_phone_suite_goes_back_online() -> None:
    suite = _suite(transport=TransportKind.PSTN, phone_number="+14155550123")

    assert prompts.choose_transport(suite, transport="web") == "webrtc"


def test_asking_for_web_keeps_however_the_suite_normally_connects() -> None:
    suite = _suite(transport=TransportKind.TEXT)

    assert prompts.choose_transport(suite, transport="web") == "text"


def test_an_unknown_transport_is_rejected_with_the_two_real_choices(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(typer.Exit):
        prompts.choose_transport(_suite(), transport="carrier-pigeon")

    assert "web or phone" in capsys.readouterr().out


def test_a_non_interactive_run_never_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompts, "is_interactive", lambda: False)
    asked = _answer(monkeypatch)

    assert prompts.choose_transport(_suite()) == "webrtc"
    assert asked == []


def test_the_prompt_defaults_to_the_suites_own_transport(
    interactive: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    defaults: list[str] = []

    def fake_prompt(label: str, *args: Any, **kwargs: Any) -> str:
        defaults.append(str(kwargs.get("default", "")))
        return str(kwargs.get("default", ""))

    monkeypatch.setattr(typer, "prompt", fake_prompt)

    assert prompts.choose_transport(_suite()) == "webrtc"
    assert prompts.choose_transport(_suite(transport=TransportKind.PSTN)) == "pstn"
    assert defaults == ["web", "phone"]


def test_answering_phone_at_the_prompt_switches_to_a_call(
    interactive: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer(monkeypatch, "phone")

    assert prompts.choose_transport(_suite()) == "pstn"


# --- finding the agent's number ---------------------------------------------


def test_the_flag_wins_and_is_normalized_and_remembered() -> None:
    number = prompts.ensure_agent_number(_suite(), phone=" +1 415-555-0123 ")

    assert number == "+14155550123"
    assert saved_agent_number(platform="retell", agent_id=AGENT) == "+14155550123"


def test_a_suite_that_declares_its_number_needs_no_picker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _answer(monkeypatch)
    suite = _suite(transport=TransportKind.PSTN, phone_number="+14155550123")

    assert prompts.ensure_agent_number(suite) == "+14155550123"
    assert asked == []


def test_the_second_run_reuses_the_remembered_pick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts.ensure_agent_number(_suite(), phone="+14155550123")
    asked = _answer(monkeypatch)

    assert prompts.ensure_agent_number(_suite()) == "+14155550123"
    assert asked == []


def test_a_number_that_cannot_be_dialed_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(typer.Exit):
        prompts.ensure_agent_number(_suite(), phone="555-0123")

    assert "E.164" in capsys.readouterr().out


def test_without_a_terminal_the_number_has_to_come_from_a_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(prompts, "is_interactive", lambda: False)

    with pytest.raises(typer.Exit):
        prompts.ensure_agent_number(_suite())

    assert "--phone" in capsys.readouterr().out


def test_the_picker_offers_the_numbers_bound_to_the_agent(
    interactive: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        prompts,
        "_discover_agent_numbers",
        lambda **_: [
            AgentNumber(number="+14155550123", label="Main line", bound=True),
            AgentNumber(number="+14155550199", label="Support", bound=False),
        ],
    )
    _answer(monkeypatch, "2")

    assert prompts.ensure_agent_number(_suite()) == "+14155550199"
    out = capsys.readouterr().out
    assert "Main line" in out and "this agent" in out


def test_a_platform_that_cannot_be_queried_just_asks(
    interactive: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prompts, "_discover_agent_numbers", lambda **_: [])
    asked = _answer(monkeypatch, "+14155550123")

    assert prompts.ensure_agent_number(_suite()) == "+14155550123"
    assert any("E.164" in label for label in asked)


# --- the optional extra -----------------------------------------------------


def test_a_missing_extra_is_reported_before_anything_is_dialed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import importlib.util

    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: None if name == "pyVoIP" else object(),
    )

    with pytest.raises(typer.Exit):
        prompts.require_pstn_extra()

    out = capsys.readouterr().out
    assert "pyVoIP" in out and "uv sync --extra pstn" in out


def test_an_installed_extra_passes_quietly() -> None:
    prompts.require_pstn_extra()


# --- end to end through the command -----------------------------------------


@pytest.fixture()
def stubbed_simulate(monkeypatch: pytest.MonkeyPatch) -> list[SuiteConfig]:
    """Run `simulate` for real up to the dial, recording the resolved config."""
    seen: list[SuiteConfig] = []

    async def fake_simulate(cfg: SuiteConfig, *_: Any, **__: Any) -> None:
        seen.append(cfg)
        raise RuntimeError("stopped before dialing")

    import wiretap.agent

    monkeypatch.setattr(wiretap.agent, "simulate_scenario", fake_simulate)
    monkeypatch.setattr(prompts, "ensure_caller_configured", lambda **_: None)
    monkeypatch.setattr(prompts, "ensure_platform_key", lambda *a, **k: None)
    monkeypatch.setattr(prompts, "require_pstn_extra", lambda: None)
    monkeypatch.setattr(prompts, "ensure_pstn_configured", lambda **_: "+14155550199")
    return seen


def _run(tmp_path: Path, suite: SuiteConfig, *args: str) -> Any:
    suites = tmp_path / "suites"
    suites.mkdir(parents=True, exist_ok=True)
    dump_suite(suite, suites / "under_test.yaml")
    return CliRunner().invoke(
        app, ["simulate", "-s", "under_test", "--all", "-q", *args]
    )


def _evaluation(tmp_path: Path) -> dict[str, Any]:
    files = list((tmp_path / "evaluations").glob("*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8"))


def test_flags_carry_a_web_suite_onto_the_phone_without_prompting(
    tmp_path: Path, stubbed_simulate: list[SuiteConfig]
) -> None:
    result = _run(
        tmp_path,
        _suite(),
        "--transport",
        "phone",
        "--phone",
        "+14155550123",
    )

    assert result.exit_code == 1  # the stub aborts every scenario
    assert stubbed_simulate[0].agent.transport is TransportKind.PSTN
    assert stubbed_simulate[0].agent.phone_number == "+14155550123"


def test_phone_runs_are_forced_to_one_call_at_a_time(
    tmp_path: Path, stubbed_simulate: list[SuiteConfig]
) -> None:
    """One softphone: a second concurrent call would collide on port and login."""
    _run(
        tmp_path,
        _suite(scenarios=3),
        "--transport",
        "phone",
        "--phone",
        "+14155550123",
        "-c",
        "3",
    )

    assert _evaluation(tmp_path)["concurrency"] == 1


def test_a_web_run_still_allows_two_at_a_time(
    tmp_path: Path, stubbed_simulate: list[SuiteConfig]
) -> None:
    _run(tmp_path, _suite(scenarios=3), "--transport", "web", "-c", "3")

    assert _evaluation(tmp_path)["concurrency"] == 2


def test_a_phone_suite_can_be_run_over_the_web_instead(
    tmp_path: Path, stubbed_simulate: list[SuiteConfig]
) -> None:
    suite = _suite(transport=TransportKind.PSTN, phone_number="+14155550123")

    _run(tmp_path, suite, "--transport", "web")

    assert stubbed_simulate[0].agent.transport is TransportKind.WEBRTC
