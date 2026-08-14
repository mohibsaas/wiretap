"""MCP tool surface — validation, shaping, and signature preservation."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
import yaml

from wiretap.mcp import tools
from wiretap.models import (
    JudgeResult,
    RuleResult,
    SimulationArtifact,
    ToolCallRecord,
    TurnRecord,
)
from wiretap.paths import ensure_layout, suites_dir
from wiretap.services.suites import save_suite_import
from wiretap.suite import DEFAULT_SUITE, load_suite

# Names a prompt-injected model might supply to escape the data directory.
HOSTILE_NAMES = [
    "../../etc/passwd",
    "/etc/passwd",
    "..",
    ".",
    "../outside",
    "nested/name",
    "back\\slash",
]

# The import tools read an empty name as "derive one from the platform", so it
# is only invalid where a name is required outright.
TRAVERSAL_NAMES = [*HOSTILE_NAMES, ""]


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the data root at tmp so tools touch nothing real."""
    root = tmp_path / ".wiretap"
    monkeypatch.setenv("WIRETAP_HOME", str(root))
    monkeypatch.chdir(tmp_path)
    ensure_layout()
    return root


@pytest.fixture
def suite_file(home: Path) -> Path:
    path = suites_dir() / "demo.yaml"
    path.write_text(DEFAULT_SUITE, encoding="utf-8")
    return path


def call(fn, *args, **kwargs):
    """Tools return JSON strings; decode for assertions."""
    return json.loads(fn(*args, **kwargs))


def _artifact(**overrides) -> SimulationArtifact:
    data = {
        "simulation_id": "sim1",
        "suite_id": "demo",
        "scenario_id": "cancel_refund",
        "scenario_name": "Cancel with refund",
        "persona_id": "priya",
        "passed": True,
        "transcript": [
            TurnRecord(role="user", text="I want to cancel my subscription"),
            TurnRecord(role="agent", text="Sure, let me pull up your account"),
        ],
        "tool_calls": [ToolCallRecord(name="lookup_account", status="ok")],
        "judge": JudgeResult(passed=True, score=0.9, verdict="pass", reason="clear"),
        "rules": RuleResult(passed=True),
    }
    data.update(overrides)
    return SimulationArtifact.model_validate(data)


# --------------------------------------------------------------------------
# Path traversal
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", TRAVERSAL_NAMES)
def test_read_tools_reject_traversal(home: Path, name: str) -> None:
    for fn in (tools.get_suite, tools.export_suite):
        assert "error" in call(fn, name), f"{fn.__name__} accepted {name!r}"


@pytest.mark.parametrize("name", TRAVERSAL_NAMES)
def test_simulate_rejects_traversal(home: Path, name: str) -> None:
    assert "error" in call(tools.simulate_suite, name)


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_import_rejects_traversal_before_any_network_call(
    home: Path, name: str
) -> None:
    # A valid platform + hostile name must fail on the name, not attempt a fetch.
    out = call(tools.import_agent, "vapi", "asst_123", name)
    assert "Invalid suite name" in out["error"]

    out = call(tools.import_livekit_agent, "room", "wss://example.test", name)
    assert "Invalid suite name" in out["error"]


def test_traversal_writes_nothing_outside_the_data_root(
    home: Path, tmp_path: Path
) -> None:
    canary = tmp_path / "canary"
    before = sorted(p.name for p in tmp_path.iterdir())

    for name in [*HOSTILE_NAMES, str(canary)]:
        call(tools.import_agent, "vapi", "asst_123", name)
        call(tools.import_livekit_agent, "room", "wss://example.test", name)
        call(tools.generate_suite, name)
        call(tools.fill_suite_scenarios, name)

    assert not canary.exists()
    assert not (canary.parent / "canary.yaml").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_save_suite_import_rejects_traversal(suite_file: Path) -> None:
    suite = load_suite(suite_file)
    for name in TRAVERSAL_NAMES:
        with pytest.raises(ValueError):
            save_suite_import(name, suite, None)


# --------------------------------------------------------------------------
# Suites
# --------------------------------------------------------------------------


def test_list_and_get_suite_round_trip(suite_file: Path) -> None:
    listed = call(tools.list_suites)
    assert [s["name"] for s in listed] == ["demo"]
    assert listed[0]["scenario_count"] == 1
    assert listed[0]["persona_count"] == 1

    suite = call(tools.get_suite, "demo")
    assert suite["name"] == "demo"
    assert [s["id"] for s in suite["scenarios"]] == ["cancel_refund"]
    assert [p["id"] for p in suite["personas"]] == ["priya"]


def test_get_suite_reports_missing_suite(home: Path) -> None:
    assert "error" in call(tools.get_suite, "nope")


def test_export_suite_returns_parseable_yaml(suite_file: Path) -> None:
    out = call(tools.export_suite, "demo")
    assert out["name"] == "demo"
    parsed = yaml.safe_load(out["yaml"])
    assert parsed["scenarios"][0]["id"] == "cancel_refund"
    # Returns text rather than accepting a destination path to write to.
    assert "path" not in out


# --------------------------------------------------------------------------
# Simulate
# --------------------------------------------------------------------------


def test_simulate_errors_on_unmatched_scenario(suite_file: Path) -> None:
    out = call(tools.simulate_suite, "demo", "does_not_exist")
    assert "error" in out
    assert "does_not_exist" in out["error"]
    # Lists what is actually available instead of silently returning nothing.
    assert "cancel_refund" in out["error"]


def test_simulate_errors_on_empty_suite(home: Path) -> None:
    empty = yaml.safe_load(DEFAULT_SUITE)
    empty["scenarios"] = []
    (suites_dir() / "empty.yaml").write_text(yaml.safe_dump(empty), encoding="utf-8")
    out = call(tools.simulate_suite, "empty")
    assert "no scenarios" in out["error"].lower()


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------


def test_import_agent_rejects_unknown_platform(home: Path) -> None:
    out = call(tools.import_agent, "not_a_platform", "abc")
    assert "Unknown platform" in out["error"]
    for platform in tools.IMPORT_PLATFORMS:
        assert platform in out["error"]


def test_import_agent_requires_agent_id(home: Path) -> None:
    assert "agent_id is required" in call(tools.import_agent, "vapi", "  ")["error"]


def test_upstream_http_errors_stay_in_band(home: Path) -> None:
    """Platform API failures must come back as {"error": ...}, not raise."""
    import httpx

    @tools._tool
    def boom() -> dict:
        raise httpx.HTTPStatusError(
            "404 Not Found",
            request=httpx.Request("GET", "https://api.example.test/agent/x"),
            response=httpx.Response(404),
        )

    assert "404" in json.loads(boom())["error"]


def test_import_livekit_requires_room(home: Path) -> None:
    assert "error" in call(tools.import_livekit_agent, "", "wss://example.test")


# --------------------------------------------------------------------------
# Payload shaping
# --------------------------------------------------------------------------


def test_summary_excludes_transcript_bodies() -> None:
    art = _artifact()
    summary = tools._summary(art)

    assert "transcript" not in summary
    assert summary["turns"] == 2
    assert summary["tool_calls"] == ["lookup_account"]
    assert summary["score"] == 0.9
    assert summary["passed"] is True
    assert summary["inconclusive"] is False

    blob = json.dumps(summary)
    assert "pull up your account" not in blob
    assert "I want to cancel my subscription" not in blob


def test_summary_flags_inconclusive() -> None:
    summary = tools._summary(_artifact(meta={"inconclusive": True}, passed=False))
    assert summary["inconclusive"] is True


def test_summary_truncates_long_judge_reason() -> None:
    summary = tools._summary(
        _artifact(
            judge=JudgeResult(passed=False, verdict="fail", reason="x" * 5000),
        )
    )
    assert len(summary["reason"]) <= 400


def test_get_simulation_returns_full_transcript(home: Path) -> None:
    from wiretap.suite import save_simulation

    save_simulation(_artifact())
    out = call(tools.get_simulation, "sim1")
    assert [t["text"] for t in out["transcript"]] == [
        "I want to cancel my subscription",
        "Sure, let me pull up your account",
    ]


def test_get_simulation_reports_missing_id(home: Path) -> None:
    assert "error" in call(tools.get_simulation, "missing")


def test_list_simulations_returns_summaries(home: Path) -> None:
    from wiretap.suite import save_simulation

    save_simulation(_artifact())
    listed = call(tools.list_simulations)
    assert len(listed) == 1
    assert "transcript" not in listed[0]
    assert listed[0]["simulation_id"] == "sim1"


def test_simulation_limit_is_clamped(home: Path) -> None:
    assert tools._limit(10**9, 20) == tools.MAX_LIMIT
    assert tools._limit(0, 20) == 1
    assert tools._limit("junk", 20) == 20


# --------------------------------------------------------------------------
# Registration contract
# --------------------------------------------------------------------------


def test_every_tool_returns_a_json_string() -> None:
    for fn in tools.TOOLS:
        assert inspect.signature(fn).return_annotation is str, fn.__name__


def test_decorator_preserves_parameter_signatures() -> None:
    params = inspect.signature(tools.simulate_suite).parameters
    assert list(params) == ["suite", "scenario", "concurrency"]
    assert params["suite"].default == "default"
    assert params["concurrency"].default == tools.DEFAULT_CONCURRENCY


def test_tools_have_docstrings_for_the_mcp_schema() -> None:
    for fn in tools.TOOLS:
        assert (fn.__doc__ or "").strip(), fn.__name__


def test_tools_module_does_not_require_the_mcp_package() -> None:
    """The extra is optional, so the tool bodies must import without it."""
    import subprocess
    import sys

    # Subprocess with `mcp` blocked at import — an in-process check would pass
    # for the wrong reason once any sibling test has imported the package.
    script = (
        "import sys\n"
        "class Block:\n"
        "    def find_module(self, name, path=None):\n"
        "        if name == 'mcp' or name.startswith('mcp.'):\n"
        "            raise ImportError('blocked')\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        return self.find_module(name, path)\n"
        "sys.meta_path.insert(0, Block())\n"
        "import wiretap.mcp.tools as t\n"
        "assert t.list_suites() and len(t.TOOLS) == 14\n"
        "print('ok')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout
