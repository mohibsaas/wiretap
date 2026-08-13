"""Importer smoke tests with mocked HTTP."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from wiretap.importers.bolna import import_bolna_agent
from wiretap.importers.elevenlabs import import_elevenlabs_agent
from wiretap.importers.livekit_agents import suite_for_livekit_agent
from wiretap.importers.synthflow import import_synthflow_agent


@respx.mock
def test_import_elevenlabs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test")
    respx.get("https://api.elevenlabs.io/v1/convai/agents/ag1").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "Support Bot",
                "conversation_config": {
                    "agent": {
                        "prompt": {"prompt": "You help with refunds."},
                        "first_message": "Hi, how can I help?",
                    }
                },
            },
        )
    )
    suite, graph = asyncio.run(import_elevenlabs_agent("ag1"))
    assert suite.agent.platform == "elevenlabs"
    assert suite.agent.agent_id == "ag1"
    assert suite.agent.token_env == "ELEVENLABS_API_KEY"
    assert graph.source_platform == "elevenlabs"
    assert "refunds" in (graph.nodes[0].prompt or "")


def test_suite_for_livekit() -> None:
    suite, graph = suite_for_livekit_agent(
        room_name="room-a",
        room_url="wss://proj.livekit.cloud",
        agent_name="Desk",
    )
    assert suite.agent.platform == "livekit"
    assert suite.agent.agent_id == "room-a"
    assert suite.agent.room_url == "wss://proj.livekit.cloud"
    assert graph.source_platform == "livekit"


@respx.mock
def test_import_synthflow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNTHFLOW_API_KEY", "sf-test")
    respx.get("https://api.synthflow.ai/v2/assistants/m1").mock(
        return_value=httpx.Response(
            200,
            json={"name": "SF Agent", "prompt": "Book appointments.", "greeting": "Hello"},
        )
    )
    suite, graph = asyncio.run(import_synthflow_agent("m1"))
    assert suite.agent.platform == "synthflow"
    assert "appointments" in (graph.nodes[0].prompt or "")


@respx.mock
def test_import_bolna(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOLNA_API_KEY", "bo-test")
    respx.get("https://api.bolna.ai/v2/agent/b1").mock(
        return_value=httpx.Response(
            200,
            json={
                "agent_config": {
                    "agent_name": "Bolna Bot",
                    "agent_welcome_message": "Hey",
                },
                "agent_prompts": {"task_1": {"system_prompt": "Collect payment info."}},
            },
        )
    )
    suite, graph = asyncio.run(import_bolna_agent("b1"))
    assert suite.agent.platform == "bolna"
    assert suite.agent.token_env == "BOLNA_API_KEY"
    assert "payment" in (graph.nodes[0].prompt or "")
