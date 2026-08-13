"""Agent brief building + sanitization before anything reaches an LLM."""

from __future__ import annotations

from pathlib import Path

from wiretap.importers.agent_graph import (
    AgentGraph,
    GraphNode,
    GraphTool,
    NodeType,
    as_str_list,
    graph_config,
)
from wiretap.models import AgentTarget, SuiteConfig
from wiretap.services.agent_brief import (
    PROMPT_EXCERPT_CAP,
    REDACTED,
    TRUNCATION_MARKER,
    brief_for_suite,
    build_agent_brief,
    end_call_phrases,
    load_agent_graph,
    sanitize_text,
)

SECRETS_PROMPT = """You are a clinic booking agent.
Your job is to book cleanings and quote the published fee.
Never promise a refund you cannot verify.
Look up records with sk-live-abcdef1234567890abcdef.
STRIPE_SECRET_KEY=sk_test_zzzzzzzzzzzzzzzzzzzzzz
Escalate through https://admin:hunter2@internal.example.com/queue
Billing is billing@example.com or +1 (415) 555-0199.
Demo account 998877665544 is safe to read.
Send header Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl
AWS id AKIAIOSFODNN7EXAMPLE is in the vault.
"""


def _graph(prompt: str = SECRETS_PROMPT, **config: object) -> AgentGraph:
    return AgentGraph(
        id="agent_1",
        name="Clinic bot",
        entry_node_id="main",
        nodes=[
            GraphNode(id="main", type=NodeType.CONVERSATION, name="main", prompt=prompt),
            GraphNode(
                id="tool_book",
                type=NodeType.LOGIC,
                name="book_appointment",
                metadata={
                    "tool": {
                        "function": {
                            "name": "book_appointment",
                            "description": "Books a slot for the caller",
                        }
                    }
                },
            ),
            GraphNode(id="handoff", type=NodeType.TRANSFER, name="transfer_to_human"),
            GraphNode(id="end", type=NodeType.END, name="end"),
        ],
        config=graph_config(**config),
    )


def test_sanitize_strips_secrets_and_contact_details() -> None:
    out = sanitize_text(SECRETS_PROMPT, cap=PROMPT_EXCERPT_CAP)

    assert "sk-live-abcdef1234567890abcdef" not in out
    assert "STRIPE_SECRET_KEY" not in out  # env-style line dropped entirely
    assert "sk_test_zzzzzzzzzzzzzzzzzzzzzz" not in out
    assert "hunter2" not in out
    assert "billing@example.com" not in out
    assert "555-0199" not in out
    assert "998877665544" not in out
    assert "eyJhbGciOiJIUzI1NiJ9" not in out
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert REDACTED in out

    # Domain language the generator actually needs must survive.
    assert "clinic booking agent" in out
    assert "Never promise a refund" in out


def test_sanitize_truncates_with_marker() -> None:
    out = sanitize_text("word " * 4000, cap=100)

    assert out.endswith(TRUNCATION_MARKER)
    assert len(out) <= 100 + len(TRUNCATION_MARKER)


def test_sanitize_redacts_before_truncating() -> None:
    """A cut must not be able to leave half a secret behind."""
    text = "prefix sk-live-abcdef1234567890abcdef suffix"
    out = sanitize_text(text, cap=len("prefix sk-live-abcdef"))

    assert "sk-live" not in out


def test_sanitize_keeps_short_numbers() -> None:
    out = sanitize_text("Refunds within 30 days, up to 2 items.", cap=500)

    assert "30 days" in out
    assert "2 items" in out


def test_brief_has_grounding_and_no_secrets() -> None:
    brief = build_agent_brief(
        _graph(
            language="en",
            end_call_phrases=as_str_list(["goodbye now", "have a nice day"]),
            first_message="Thanks for calling the clinic.",
        ),
        purpose="dental booking",
        agent_name="Clinic bot",
    )

    assert brief["agent_name"] == "Clinic bot"
    assert brief["purpose"] == "dental booking"
    assert brief["language"] == "en"
    assert brief["end_call_phrases"] == ["goodbye now", "have a nice day"]
    assert brief["first_message"] == "Thanks for calling the clinic."
    assert "Never promise a refund" in brief["summary"]

    names = [t["name"] for t in brief["tools"]]
    assert "book_appointment" in names
    assert "transfer_to_human" in names
    assert set(brief["irreversible_tools"]) == {"book_appointment", "transfer_to_human"}

    node_ids = [n["id"] for n in brief["flow_nodes"]]
    assert node_ids == ["main", "tool_book", "handoff", "end"]

    blob = repr(brief)
    for secret in ("sk-live-abcdef", "hunter2", "billing@example.com", "998877665544"):
        assert secret not in blob


def test_brief_never_includes_token_env() -> None:
    suite = SuiteConfig(
        agent=AgentTarget(platform="retell", agent_id="agent_1", token_env="RETELL_API_KEY"),
        personas=[],
        scenarios=[],
    )
    brief = build_agent_brief(_graph(), suite=suite, agent_name="Clinic bot")

    assert brief["platform"] == "retell"
    assert brief["agent_id"] == "agent_1"
    assert "token_env" not in brief
    assert "RETELL_API_KEY" not in repr(brief)


def test_brief_uses_first_class_graph_tools() -> None:
    graph = AgentGraph(
        id="agent_1",
        name="Fronter",
        entry_node_id="main",
        nodes=[GraphNode(id="main", type=NodeType.CONVERSATION, prompt="Qualify the caller.")],
        tools=[
            GraphTool(
                name="extract_update_dynamic_variable",
                type="custom",
                description="Extracts caller details",
                parameters=["zip_code", "callback_number"],
            ),
            GraphTool(name="book_estimate", type="custom"),
            GraphTool(name="end_call", type="end_call"),
        ],
    )
    brief = build_agent_brief(graph, agent_name="Fronter")

    tools = {t["name"]: t for t in brief["tools"]}
    assert set(tools) == {"extract_update_dynamic_variable", "book_estimate", "end_call"}
    assert tools["extract_update_dynamic_variable"]["parameters"] == [
        "zip_code",
        "callback_number",
    ]
    assert tools["extract_update_dynamic_variable"]["description"] == "Extracts caller details"
    # A built-in whose type equals its name should not repeat itself.
    assert "type" not in tools["end_call"]
    assert brief["irreversible_tools"] == ["book_estimate"]


def test_brief_tool_descriptions_are_sanitized() -> None:
    graph = AgentGraph(
        id="agent_1",
        entry_node_id="main",
        nodes=[GraphNode(id="main", type=NodeType.CONVERSATION, prompt="Book cleanings.")],
        tools=[
            GraphTool(
                name="charge_card",
                description="Charge via sk-live-abcdef1234567890abcdef, notify billing@example.com",
            )
        ],
    )
    brief = build_agent_brief(graph, agent_name="Clinic bot")

    blob = repr(brief["tools"])
    assert "sk-live-abcdef" not in blob
    assert "billing@example.com" not in blob
    assert REDACTED in blob
    assert brief["irreversible_tools"] == ["charge_card"]


def test_brief_merges_graph_tools_with_legacy_metadata_nodes() -> None:
    """Graphs written before AgentGraph.tools existed still ground generation."""
    graph = _graph()
    graph.tools = [GraphTool(name="refund_order", type="function")]
    brief = build_agent_brief(graph, agent_name="Clinic bot")

    names = [t["name"] for t in brief["tools"]]
    assert names[0] == "refund_order"
    assert "book_appointment" in names
    assert "transfer_to_human" in names


def test_brief_tools_alone_are_enough_grounding() -> None:
    graph = AgentGraph(
        id="agent_1",
        entry_node_id="main",
        tools=[GraphTool(name="book_estimate")],
    )

    assert build_agent_brief(graph, agent_name="Bot")["tools"] == [{"name": "book_estimate"}]


def test_brief_empty_without_a_graph() -> None:
    assert build_agent_brief(None, purpose="anything", agent_name="Bot") == {}
    assert end_call_phrases({}) == []
    assert end_call_phrases(None) == []


def test_brief_empty_when_graph_has_no_substance() -> None:
    """Name and purpose alone are not grounding — that is the purpose-only path."""
    bare = AgentGraph(id="x", name="Bot", entry_node_id="main")

    assert build_agent_brief(bare, purpose="something", agent_name="Bot") == {}


def test_graph_config_survives_disk_roundtrip(tmp_path: Path) -> None:
    graph = _graph(language="en", end_call_phrases=["goodbye now"])
    target = tmp_path / ".wiretap" / "graphs" / "clinic.graph.json"
    target.parent.mkdir(parents=True)
    target.write_text(graph.model_dump_json(indent=2), encoding="utf-8")

    loaded = load_agent_graph("clinic", cwd=tmp_path)
    assert loaded is not None
    assert loaded.config["language"] == "en"
    assert loaded.config["end_call_phrases"] == ["goodbye now"]

    brief = brief_for_suite("clinic", agent_name="Clinic bot", cwd=tmp_path)
    assert brief["end_call_phrases"] == ["goodbye now"]


def test_load_agent_graph_missing_or_corrupt(tmp_path: Path) -> None:
    assert load_agent_graph("nope", cwd=tmp_path) is None
    assert load_agent_graph("", cwd=tmp_path) is None

    corrupt = tmp_path / ".wiretap" / "graphs" / "bad.graph.json"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("{not json", encoding="utf-8")
    assert load_agent_graph("bad", cwd=tmp_path) is None

    assert brief_for_suite("bad", cwd=tmp_path) == {}
