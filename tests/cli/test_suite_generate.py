"""suite generate create / refill behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wiretap.cli.main import app
from wiretap.importers.agent_graph import AgentGraph, GraphNode, GraphTool, NodeType
from wiretap.models import AgentTarget, SuiteConfig, TransportKind
from wiretap.paths import WIRETAP_HOME_ENV
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
    # Isolate CLI data under the test dir (global default is ~/.wiretap)
    monkeypatch.setenv(WIRETAP_HOME_ENV, str(tmp_path / ".wiretap"))
    monkeypatch.setattr(
        "wiretap.cli.prompts.ensure_caller_configured", lambda **kwargs: None
    )
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
            phone_number="+14155550123",
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
    # Dropping this would silently make the rebound suite undialable by phone.
    assert suite.agent.phone_number == "+14155550123"
    assert len(suite.scenarios) == 1


def test_refill_grounds_in_graph_on_disk(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Refill has no live API — the imported config must come off disk."""
    seen: list[str] = []

    def fake_complete(*, model, messages, temperature=0.4, max_tokens=512):
        seen.extend(m["content"] for m in messages if m["role"] == "user")
        return json.dumps(_fake_tests(1, "task"))

    monkeypatch.setattr("wiretap.services.generator.complete", fake_complete)

    suite = SuiteConfig(
        agent=AgentTarget(
            transport=TransportKind.WEBRTC,
            platform="retell",
            agent_id="agent_abc",
            token_env="RETELL_API_KEY",
        ),
        personas=[],
        scenarios=[],
    )
    dump_suite(suite, tmp_path / ".wiretap" / "suites" / "clinic.yaml")

    graph = AgentGraph(
        id="agent_abc",
        name="Clinic bot",
        entry_node_id="main",
        nodes=[
            GraphNode(
                id="main",
                type=NodeType.CONVERSATION,
                name="main",
                prompt=(
                    "You are a dental clinic scheduler.\n"
                    "Your job is to book cleanings and quote the published fee."
                ),
            )
        ],
        config={"language": "en", "end_call_phrases": ["goodbye now"]},
    )
    graphs = tmp_path / ".wiretap" / "graphs"
    graphs.mkdir(parents=True, exist_ok=True)
    (graphs / "clinic.graph.json").write_text(graph.model_dump_json(), encoding="utf-8")

    result = runner.invoke(
        app, ["suite", "generate", "-s", "clinic", "-C", "task", "-n", "1"]
    )
    assert result.exit_code == 0, result.output
    # Rich wraps the status line, so match a fragment that cannot be split.
    assert "grounded in" in result.output

    payload = "\n".join(seen)
    assert "agent_brief" in payload
    assert "dental clinic scheduler" in payload
    assert "goodbye now" in payload

    # Still a valid suite, and the purpose suffix is gone once grounded.
    refilled = load_suite(tmp_path / ".wiretap" / "suites" / "clinic.yaml")
    assert len(refilled.scenarios) == 1
    assert "Align with purpose" not in refilled.scenarios[0].success_criteria


def test_new_suite_grounds_in_the_agent_from_graph(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A new suite bound with --agent-from reads that agent's graph, not its own."""
    seen: list[str] = []

    def fake_complete(*, model, messages, temperature=0.4, max_tokens=512):
        seen.extend(m["content"] for m in messages if m["role"] == "user")
        return json.dumps(_fake_tests(1, "task"))

    monkeypatch.setattr("wiretap.services.generator.complete", fake_complete)

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
    dump_suite(src, tmp_path / ".wiretap" / "suites" / "clinic.yaml")

    graph = AgentGraph(
        id="agent_abc",
        name="Clinic bot",
        entry_node_id="main",
        nodes=[
            GraphNode(
                id="main",
                type=NodeType.CONVERSATION,
                name="main",
                prompt="You are a dental clinic scheduler. Your job is to book cleanings.",
            )
        ],
        tools=[GraphTool(name="book_appointment", description="Books a slot")],
    )
    graphs = tmp_path / ".wiretap" / "graphs"
    graphs.mkdir(parents=True, exist_ok=True)
    (graphs / "clinic.graph.json").write_text(graph.model_dump_json(), encoding="utf-8")

    result = runner.invoke(
        app,
        ["suite", "generate", "-s", "newtests", "-C", "task", "-n", "1", "--agent-from", "clinic"],
    )
    assert result.exit_code == 0, result.output

    payload = "\n".join(seen)
    assert "dental clinic scheduler" in payload
    assert "book_appointment" in payload

    # The new suite still inherits the bound agent target.
    out = load_suite(tmp_path / ".wiretap" / "suites" / "newtests.yaml")
    assert out.agent.platform == "retell"
    assert out.agent.agent_id == "agent_abc"
    assert out.agent.token_env == "RETELL_API_KEY"


def test_expected_tools_kept_only_when_the_agent_has_them(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A hallucinated tool name would fail every run against an expectation the
    agent could never satisfy, so only names from the graph survive."""

    def fake_complete(*, model, messages, temperature=0.4, max_tokens=512):
        tests = _fake_tests(1, "task")
        tests[0]["expected_tools"] = ["book_appointment", "refund_card"]
        return json.dumps(tests)

    monkeypatch.setattr("wiretap.services.generator.complete", fake_complete)

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
    dump_suite(src, tmp_path / ".wiretap" / "suites" / "clinic.yaml")

    graph = AgentGraph(
        id="agent_abc",
        name="Clinic bot",
        entry_node_id="main",
        nodes=[
            GraphNode(
                id="main",
                type=NodeType.CONVERSATION,
                name="main",
                prompt="You are a dental clinic scheduler.",
            )
        ],
        tools=[GraphTool(name="book_appointment", description="Books a slot")],
    )
    graphs = tmp_path / ".wiretap" / "graphs"
    graphs.mkdir(parents=True, exist_ok=True)
    (graphs / "clinic.graph.json").write_text(graph.model_dump_json(), encoding="utf-8")

    result = runner.invoke(app, ["suite", "generate", "-s", "clinic", "-C", "task", "-n", "1"])
    assert result.exit_code == 0, result.output

    scenario = load_suite(tmp_path / ".wiretap" / "suites" / "clinic.yaml").scenarios[0]
    assert scenario.expected_tools == ["book_appointment"]


def test_expected_tools_empty_without_a_graph(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With no imported agent there is no tool list to validate against."""

    def fake_complete(*, model, messages, temperature=0.4, max_tokens=512):
        tests = _fake_tests(1, "task")
        tests[0]["expected_tools"] = ["book_appointment"]
        return json.dumps(tests)

    monkeypatch.setattr("wiretap.services.generator.complete", fake_complete)

    result = runner.invoke(
        app,
        ["suite", "generate", "-s", "loose", "-C", "task", "-n", "1", "-p", "Booking"],
    )
    assert result.exit_code == 0, result.output
    scenario = load_suite(tmp_path / ".wiretap" / "suites" / "loose.yaml").scenarios[0]
    assert scenario.expected_tools == []


def test_generate_missing_inputs_errors(runner: CliRunner) -> None:
    result = runner.invoke(app, ["suite", "generate", "-s", "orphan", "-C", "task"])
    assert result.exit_code == 1
    assert "--purpose" in result.output or "purpose" in result.output.lower()
