"""suite generate create / refill behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wiretap.cli.main import app
from wiretap.models import AgentTarget, SuiteConfig, TransportKind
from wiretap.suite import dump_suite, load_suite


def _fake_tests(count: int, category: str) -> list[dict]:
    return [
        {
            "name": f"{category.title()} case {i + 1}",
            "identity": f"Caller for {category} {i + 1}",
            "goal": f"Goal {category} {i + 1}",
            "say": f"Hello {category} {i + 1}",
            "success": f"Success {category} {i + 1}",
            "excludes": [],
        }
        for i in range(count)
    ]


@pytest.fixture()
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.chdir(tmp_path)
    return CliRunner()


def test_generate_new_suite_from_purpose(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_complete(*, model, messages, temperature=0.4, max_tokens=512):
        return json.dumps(_fake_tests(2, "task"))

    monkeypatch.setattr("wiretap.services.generator.complete", fake_complete)

    result = runner.invoke(
        app,
        [
            "suite",
            "generate",
            "-s",
            "new testsuite",
            "-C",
            "task",
            "-n",
            "2",
            "-p",
            "Appointment booking assistant",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "new_testsuite" in result.output
    path = tmp_path / ".wiretap" / "suites" / "new_testsuite.yaml"
    assert path.is_file()
    suite = load_suite(path)
    assert suite.agent.platform is None  # custom stub
    assert suite.agent.transport == TransportKind.TEXT
    assert len(suite.scenarios) == 2
    assert all(s.category == "task" for s in suite.scenarios)


def test_generate_new_suite_agent_from(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_complete(*, model, messages, temperature=0.4, max_tokens=512):
        return json.dumps(_fake_tests(1, "task"))

    monkeypatch.setattr("wiretap.services.generator.complete", fake_complete)

    # Seed an imported-looking suite
    src = SuiteConfig(
        agent=AgentTarget(
            transport=TransportKind.WEBRTC,
            platform="retell",
            agent_id="agent_abc",
            token_env="RETELL_API_KEY",
        ),
        personas=[],
        scenarios=[],
    )
    dump_suite(src, tmp_path / ".wiretap" / "suites" / "retell_agent_abc.yaml")

    result = runner.invoke(
        app,
        [
            "suite",
            "generate",
            "-s",
            "booking_tests",
            "-C",
            "task",
            "-n",
            "1",
            "--agent-from",
            "retell_agent_abc",
            "-p",
            "Booking flows",
        ],
    )
    assert result.exit_code == 0, result.output
    suite = load_suite(tmp_path / ".wiretap" / "suites" / "booking_tests.yaml")
    assert suite.agent.platform == "retell"
    assert suite.agent.agent_id == "agent_abc"
    assert suite.agent.token_env == "RETELL_API_KEY"
    assert len(suite.scenarios) == 1


def test_generate_missing_inputs_errors(runner: CliRunner) -> None:
    result = runner.invoke(app, ["suite", "generate", "-s", "orphan", "-C", "task"])
    assert result.exit_code == 1
    assert "--purpose" in result.output or "purpose" in result.output.lower()
