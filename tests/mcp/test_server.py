"""Registration against the real MCP package, when the extra is installed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wiretap.mcp import tools

pytest.importorskip("mcp", reason="requires the optional mcp extra")

from wiretap.mcp.server import build_server


@pytest.fixture
def server():
    return build_server()


async def _tool_list(server):
    listed = server.list_tools()
    if hasattr(listed, "__await__"):
        listed = await listed
    return listed


def _schema(tool):
    # 2.x renamed the field to input_schema.
    return getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", {}) or {}


@pytest.mark.anyio
async def test_every_tool_registers(server) -> None:
    listed = await _tool_list(server)
    assert {t.name for t in listed} == {f.__name__ for f in tools.TOOLS}


@pytest.mark.anyio
async def test_schemas_keep_parameters_and_required_fields(server) -> None:
    by_name = {t.name: _schema(t) for t in await _tool_list(server)}

    # The @_tool decorator must not collapse signatures into (*args, **kwargs).
    assert list(by_name["simulate_suite"]["properties"]) == [
        "suite",
        "scenario",
        "concurrency",
    ]
    assert by_name["simulate_suite"].get("required", []) == []
    assert by_name["get_suite"]["required"] == ["name"]
    assert by_name["import_agent"]["required"] == ["platform", "agent_id"]


@pytest.mark.anyio
async def test_every_tool_exposes_a_description(server) -> None:
    for tool in await _tool_list(server):
        assert (tool.description or "").strip(), tool.name


@pytest.mark.anyio
async def test_traversal_is_rejected_through_a_real_call(
    server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WIRETAP_HOME", str(tmp_path / ".wiretap"))
    result = await server.call_tool("get_suite", {"name": "../../etc/passwd"})

    text = "".join(
        block.text for block in getattr(result, "content", []) if hasattr(block, "text")
    )
    assert "Invalid suite name" in json.loads(text)["error"]


@pytest.fixture
def anyio_backend():
    return "asyncio"
