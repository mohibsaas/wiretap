"""Retell live transcript finalization (interim vs complete utterances)."""

from __future__ import annotations

import json

from wiretap.transport.retell import RetellTransport


def _update(*utterances: dict) -> bytes:
    return json.dumps({"event_type": "update", "transcript": list(utterances)}).encode()


def _event(event_type: str) -> bytes:
    return json.dumps({"event_type": event_type}).encode()


def test_growing_agent_prefixes_commit_once_on_stop() -> None:
    t = RetellTransport()
    t._handle_data(_event("agent_start_talking"))
    t._handle_data(_update({"role": "agent", "content": "Hi,"}))
    t._handle_data(_update({"role": "agent", "content": "Hi, thanks"}))
    t._handle_data(_update({"role": "agent", "content": "Hi, thanks so much"}))
    assert t._pending.empty()
    assert t._draft_agent == "Hi, thanks so much"

    t._handle_data(_event("agent_stop_talking"))
    assert t._pending.qsize() == 1
    assert t._pending.get_nowait().text == "Hi, thanks so much"


def test_user_turn_finalizes_open_agent_draft() -> None:
    t = RetellTransport()
    t._handle_data(
        _update(
            {"role": "agent", "content": "How can I help?"},
            {"role": "user", "content": "I need an update."},
        )
    )
    assert t._pending.qsize() == 1
    assert t._pending.get_nowait().text == "How can I help?"


def test_does_not_recommit_same_final_utterance() -> None:
    t = RetellTransport()
    t._handle_data(_update({"role": "agent", "content": "Hello there."}))
    t._handle_data(_event("agent_stop_talking"))
    t._handle_data(_update({"role": "agent", "content": "Hello there."}))
    t._handle_data(_event("agent_stop_talking"))
    assert t._pending.qsize() == 1
