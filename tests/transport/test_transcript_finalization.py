"""Cross-provider agent transcript finalization."""

from __future__ import annotations

import json

from wiretap.transport.base import Inbound
from wiretap.transport.livekit_agents import LiveKitTransport
from wiretap.transport.transcript_util import (
    accept_final_utterance,
    is_vapi_final_transcript,
)
from wiretap.transport.vapi_ws import VapiWebSocketTransport


def test_accept_final_prefers_longer_over_prefix() -> None:
    seen: set[str] = set()
    assert accept_final_utterance("Hi,", seen) == "Hi,"
    assert accept_final_utterance("Hi, thanks", seen) == "Hi, thanks"
    assert "Hi," not in seen
    assert accept_final_utterance("Hi,", seen) is None


def test_vapi_skips_partial_assistant_transcripts() -> None:
    assert is_vapi_final_transcript({"transcriptType": "partial"}) is False
    assert is_vapi_final_transcript({"transcriptType": "final"}) is True
    assert is_vapi_final_transcript({}) is True


def test_vapi_ws_only_enqueues_final() -> None:
    t = VapiWebSocketTransport()
    for payload in (
        {
            "type": "transcript",
            "role": "assistant",
            "transcriptType": "partial",
            "transcript": "Hi,",
        },
        {
            "type": "transcript",
            "role": "assistant",
            "transcriptType": "partial",
            "transcript": "Hi, thanks",
        },
        {
            "type": "transcript",
            "role": "assistant",
            "transcriptType": "final",
            "transcript": "Hi, thanks so much.",
        },
    ):
        if not is_vapi_final_transcript(payload):
            continue
        accepted = accept_final_utterance(
            str(payload.get("transcript") or ""), t._seen_agent
        )
        if accepted:
            t._pending.put_nowait(Inbound(text=accepted))
    assert t._pending.qsize() == 1
    assert t._pending.get_nowait().text == "Hi, thanks so much."


def test_livekit_retell_style_commits_on_stop() -> None:
    t = LiveKitTransport()
    t._handle_data(json.dumps({"event_type": "agent_start_talking"}).encode())
    t._handle_data(
        json.dumps(
            {
                "event_type": "update",
                "transcript": [{"role": "agent", "content": "Hi,"}],
            }
        ).encode()
    )
    t._handle_data(
        json.dumps(
            {
                "event_type": "update",
                "transcript": [{"role": "agent", "content": "Hi, thanks so much"}],
            }
        ).encode()
    )
    assert t._pending.empty()
    t._handle_data(json.dumps({"event_type": "agent_stop_talking"}).encode())
    assert t._pending.qsize() == 1
    assert t._pending.get_nowait().text == "Hi, thanks so much"
