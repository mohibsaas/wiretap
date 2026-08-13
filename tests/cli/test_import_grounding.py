"""wiretap import → grounded generation, end to end with mocked HTTP + LLM."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from wiretap.cli.main import app
from wiretap.importers.agent_graph import AgentGraph
from wiretap.paths import WIRETAP_HOME_ENV
from wiretap.suite import load_suite

VAPI_ASSISTANT = {
    "name": "Clinic Scheduler",
    "firstMessage": "Thanks for calling the clinic.",
    "endCallPhrases": ["goodbye now"],
    "transcriber": {"language": "en"},
    "voice": {"voiceId": "voice_123"},
    "model": {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a dental clinic scheduler.\n"
                    "Your job is to book cleanings and quote the published fee.\n"
                    "Never promise a refund you cannot verify.\n"
                    "Internal lookup uses sk-live-abcdef1234567890abcdef.\n"
                    "Escalations go to ops@example.com or +1 (415) 555-0199."
                ),
            }
        ],
        "tools": [
            {
                "function": {
                    "name": "book_appointment",
                    "description": "Books a cleaning slot",
                }
            }
        ],
    },
}


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep data under the test dir and skip the interactive caller wizard."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(WIRETAP_HOME_ENV, str(tmp_path / ".wiretap"))
    monkeypatch.setenv("VAPI_API_KEY", "vapi-test")
    monkeypatch.setattr(
        "wiretap.cli.prompts.ensure_caller_configured", lambda **kwargs: None
    )


@respx.mock
def test_import_vapi_grounds_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    respx.get("https://api.vapi.ai/assistant/asst_1").mock(
        return_value=httpx.Response(200, json=VAPI_ASSISTANT)
    )

    seen: list[str] = []

    def fake_complete(*, model, messages, temperature=0.4, max_tokens=512):
        seen.extend(m["content"] for m in messages if m["role"] == "user")
        return json.dumps(
            [
                {
                    "name": "Books a cleaning",
                    "identity": "A patient due for a cleaning",
                    "goal": "Book the next available slot",
                    "say": "Hi, I'd like to book a cleaning.",
                    "success": "Agent books or offers a slot without inventing a price.",
                    "excludes": [],
                }
            ]
        )

    monkeypatch.setattr("wiretap.services.generator.complete", fake_complete)

    result = CliRunner().invoke(
        app,
        ["import", "vapi", "--assistant-id", "asst_1", "--name", "clinic", "-C", "task", "-n", "1"],
    )
    assert result.exit_code == 0, result.output

    payload = "\n".join(seen)
    # Imported config reached the model...
    assert "agent_brief" in payload
    assert "dental clinic scheduler" in payload
    assert "book_appointment" in payload
    assert "goodbye now" in payload
    # ...but its secrets and contact details did not.
    assert "sk-live-abcdef1234567890abcdef" not in payload
    assert "ops@example.com" not in payload
    assert "555-0199" not in payload

    graph = AgentGraph.model_validate_json(
        (tmp_path / ".wiretap" / "graphs" / "clinic.graph.json").read_text(encoding="utf-8")
    )
    assert graph.config["end_call_phrases"] == ["goodbye now"]
    assert graph.config["language"] == "en"
    assert graph.config["voice_id"] == "voice_123"

    suite = load_suite(tmp_path / ".wiretap" / "suites" / "clinic.yaml")
    assert [s.category for s in suite.scenarios] == ["task"]


@respx.mock
def test_import_smoke_only_skips_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _isolate(monkeypatch, tmp_path)
    respx.get("https://api.vapi.ai/assistant/asst_1").mock(
        return_value=httpx.Response(200, json=VAPI_ASSISTANT)
    )

    def boom(**kwargs):  # pragma: no cover - must never be called
        raise AssertionError("--smoke-only must not call the LLM")

    monkeypatch.setattr("wiretap.services.generator.complete", boom)

    result = CliRunner().invoke(
        app,
        ["import", "vapi", "--assistant-id", "asst_1", "--name", "clinic", "--smoke-only"],
    )
    assert result.exit_code == 0, result.output

    suite = load_suite(tmp_path / ".wiretap" / "suites" / "clinic.yaml")
    assert any(s.id == "smoke" for s in suite.scenarios)
