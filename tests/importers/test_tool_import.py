"""Tool capture per platform, with mocked HTTP.

Every platform asserts two things: the tools land in the IR, and the tool's
transport block (url / secret / token) does not.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from wiretap.importers.bolna import import_bolna_agent
from wiretap.importers.elevenlabs import import_elevenlabs_agent
from wiretap.importers.retell import import_retell_agent
from wiretap.importers.synthflow import import_synthflow_agent
from wiretap.importers.vapi import import_vapi_assistant

WEBHOOK = "https://hooks.internal.example.com/collect"
SECRET = "sk_live_notarealkey1234567890"


def _assert_no_transport(graph) -> None:
    blob = graph.model_dump_json()
    for leaked in (WEBHOOK, SECRET, "hooks.internal.example.com"):
        assert leaked not in blob


@respx.mock
def test_retell_imports_general_and_state_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETELL_API_KEY", "re-test")
    respx.get("https://api.retellai.com/get-agent/ag1").mock(
        return_value=httpx.Response(
            200,
            json={
                "agent_name": "Fronter",
                "response_engine": {"type": "retell-llm", "llm_id": "llm1"},
            },
        )
    )
    respx.get("https://api.retellai.com/get-retell-llm/llm1").mock(
        return_value=httpx.Response(
            200,
            json={
                "general_prompt": "Qualify the caller.",
                "starting_state": "intake",
                "general_tools": [
                    {"type": "end_call", "name": "end_call"},
                    {
                        "type": "custom",
                        "name": "extract_update_dynamic_variable",
                        "description": "Extracts caller details",
                        "url": WEBHOOK,
                        "parameters": {"properties": {"zip_code": {}, "callback_number": {}}},
                    },
                ],
                "states": [
                    {
                        "name": "intake",
                        "state_prompt": "Collect the zip code.",
                        "tools": [
                            {
                                "type": "transfer_call",
                                "name": "transfer_to_coordinator",
                                "url": WEBHOOK,
                            },
                            # Repeat of a general tool — adds no capability.
                            {"type": "end_call", "name": "end_call"},
                        ],
                    }
                ],
            },
        )
    )

    _suite, graph = asyncio.run(import_retell_agent("ag1"))

    assert graph.tool_names() == [
        "end_call",
        "extract_update_dynamic_variable",
        "transfer_to_coordinator",
    ]
    extract = graph.tools[1]
    assert extract.parameters == ["zip_code", "callback_number"]
    assert extract.description == "Extracts caller details"
    # State tools stay attributed to their state; general tools are unscoped.
    assert graph.tools[0].node_id == ""
    assert graph.tools[2].node_id == "intake"
    _assert_no_transport(graph)


@respx.mock
def test_retell_without_tools_stays_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETELL_API_KEY", "re-test")
    respx.get("https://api.retellai.com/get-agent/ag2").mock(
        return_value=httpx.Response(
            200, json={"agent_name": "Bare", "response_engine": {"llm_id": "llm2"}}
        )
    )
    respx.get("https://api.retellai.com/get-retell-llm/llm2").mock(
        return_value=httpx.Response(200, json={"general_prompt": "Say hi."})
    )

    _suite, graph = asyncio.run(import_retell_agent("ag2"))

    assert graph.tools == []


@respx.mock
def test_vapi_tools_do_not_persist_server_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAPI_API_KEY", "va-test")
    respx.get("https://api.vapi.ai/assistant/asst1").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "Support",
                "model": {
                    "messages": [{"role": "system", "content": "You handle refunds."}],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "refund_order",
                                "description": "Issues a refund",
                                "parameters": {"properties": {"order_id": {}}},
                            },
                            "server": {
                                "url": WEBHOOK,
                                "secret": SECRET,
                                "headers": {"Authorization": f"Bearer {SECRET}"},
                            },
                        },
                        {"type": "transferCall"},
                    ],
                },
            },
        )
    )

    _suite, graph = asyncio.run(import_vapi_assistant("asst1"))

    assert graph.tool_names() == ["refund_order", "transferCall"]
    assert graph.tools[0].parameters == ["order_id"]
    _assert_no_transport(graph)
    # The flow node stays for coverage hints, but carries no payload.
    node = next(n for n in graph.nodes if n.id == "tool_refund_order")
    assert node.metadata == {"tool_type": "function"}


@respx.mock
def test_elevenlabs_resolves_referenced_tool_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-test")
    respx.get("https://api.elevenlabs.io/v1/convai/agents/ag1").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "Support Bot",
                "conversation_config": {
                    "agent": {
                        "prompt": {
                            "prompt": "You help with refunds.",
                            "tools": [{"type": "system", "name": "end_call"}],
                            "tool_ids": ["tool_a", "tool_missing"],
                        }
                    }
                },
            },
        )
    )
    respx.get("https://api.elevenlabs.io/v1/convai/tools/tool_a").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "tool_a",
                "tool_config": {
                    "type": "webhook",
                    "name": "book_estimate",
                    "description": "Books an estimate",
                    "api_schema": {
                        "url": WEBHOOK,
                        "request_body_schema": {"properties": {"slot": {}}},
                    },
                },
            },
        )
    )
    respx.get("https://api.elevenlabs.io/v1/convai/tools/tool_missing").mock(
        return_value=httpx.Response(404, json={"detail": "gone"})
    )

    _suite, graph = asyncio.run(import_elevenlabs_agent("ag1"))

    assert graph.tool_names() == ["end_call", "book_estimate"]
    assert graph.tools[1].parameters == ["slot"]
    _assert_no_transport(graph)


@respx.mock
def test_bolna_parses_json_encoded_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOLNA_API_KEY", "bo-test")
    respx.get("https://api.bolna.ai/v2/agent/b1").mock(
        return_value=httpx.Response(
            200,
            json={
                "agent_config": {
                    "agent_name": "Bolna Bot",
                    "tasks": [
                        {
                            "tools_config": {
                                "api_tools": {
                                    "tools": json.dumps(
                                        [
                                            {
                                                "type": "function",
                                                "function": {
                                                    "name": "check_slot",
                                                    "description": "Checks a slot",
                                                    "parameters": {"properties": {"day": {}}},
                                                },
                                            }
                                        ]
                                    ),
                                    "tools_params": {
                                        "check_slot": {
                                            "url": WEBHOOK,
                                            "api_token": SECRET,
                                        }
                                    },
                                }
                            }
                        }
                    ],
                },
                "agent_prompts": {"task_1": {"system_prompt": "Book slots."}},
            },
        )
    )

    _suite, graph = asyncio.run(import_bolna_agent("b1"))

    assert graph.tool_names() == ["check_slot"]
    assert graph.tools[0].parameters == ["day"]
    _assert_no_transport(graph)


@respx.mock
def test_synthflow_reads_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNTHFLOW_API_KEY", "sf-test")
    respx.get("https://api.synthflow.ai/v2/assistants/m1").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "SF Agent",
                "prompt": "Book appointments.",
                "actions": [
                    {
                        "name": "send_sms",
                        "description": "Texts a confirmation",
                        "url": WEBHOOK,
                    }
                ],
            },
        )
    )

    _suite, graph = asyncio.run(import_synthflow_agent("m1"))

    assert graph.tool_names() == ["send_sms"]
    _assert_no_transport(graph)
