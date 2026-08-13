"""Per-platform tool-call normalization, from recorded response shapes."""

from wiretap.toolcalls import elevenlabs, retell, tool_diff, vapi

RETELL_PAYLOAD = {
    "call_id": "call_abc",
    "transcript_with_tool_calls": [
        {"role": "agent", "content": "Hi, thank you for calling."},
        {"role": "user", "content": "I need a driveway poured, I'm in 80301."},
        {
            "role": "tool_call_invocation",
            "tool_call_id": "call_9fA2",
            "name": "extract_update_dynamic_variable",
            "arguments": '{"ZipCode":"80301","CallbackNumber":"4158923245"}',
        },
        {
            "role": "tool_call_result",
            "tool_call_id": "call_9fA2",
            "content": '{"ok":true}',
            "successful": True,
        },
        {"role": "agent", "content": "Great, we offer free estimates."},
        {
            "role": "tool_call_invocation",
            "tool_call_id": "call_ff01",
            "name": "transfer_call",
            "arguments": '{"reason":"caller asked for a manager"}',
        },
        {
            "role": "tool_call_result",
            "tool_call_id": "call_ff01",
            "content": "no agent available",
            "successful": False,
        },
    ],
}

VAPI_PAYLOAD = {
    "id": "call-uuid",
    "messages": [
        {"role": "bot", "message": "Thank you for calling."},
        {"role": "user", "message": "Info about patient Max please."},
        {
            "role": "tool_calls",
            "secondsFromStart": 9.858,
            "toolCalls": [
                {
                    "id": "call_rnm9",
                    "type": "function",
                    "function": {
                        "name": "search_patient",
                        "arguments": '{"full_name": "Max"}',
                    },
                }
            ],
        },
        {
            "name": "search_patient",
            "role": "tool_call_result",
            "toolCallId": "call_rnm9",
            "result": "No result returned.",
        },
    ],
}

ELEVEN_PAYLOAD = {
    "conversation_id": "conv_123",
    "status": "done",
    "transcript": [
        {"role": "user", "message": "Hello", "time_in_call_secs": 3},
        {
            "role": "agent",
            "message": "Checking now",
            "time_in_call_secs": 7,
            "tool_calls": [
                {
                    "request_id": "req_1",
                    "tool_name": "check_availability",
                    "params_as_json": '{"date":"2026-08-14"}',
                    "tool_has_been_called": True,
                }
            ],
            "tool_results": [
                {
                    "request_id": "req_1",
                    "tool_name": "check_availability",
                    "result_value": "3 slots open",
                    "is_error": False,
                }
            ],
        },
    ],
}


def test_retell_pairs_invocations_with_results() -> None:
    records = retell.normalize(RETELL_PAYLOAD)
    assert [r.name for r in records] == [
        "extract_update_dynamic_variable",
        "transfer_call",
    ]
    first, second = records
    assert first.status == "ok"
    assert first.arguments["ZipCode"] == "80301"
    # Two utterances precede the call, so it renders before transcript index 2.
    assert first.turn_index == 2
    assert second.status == "error"
    assert second.result_summary == "no agent available"
    # Retell reports no timing for tool entries.
    assert first.at_seconds is None


def test_retell_redacts_pii_in_arguments() -> None:
    records = retell.normalize(RETELL_PAYLOAD)
    args = records[0].arguments
    assert args["CallbackNumber"] == "[REDACTED]"
    assert "4158923245" not in str(args)
    # A 5-digit zip is not a phone number and must survive.
    assert args["ZipCode"] == "80301"


def test_retell_prefers_scrubbed_transcript() -> None:
    payload = dict(RETELL_PAYLOAD)
    payload["scrubbed_transcript_with_tool_calls"] = [
        {
            "role": "tool_call_invocation",
            "tool_call_id": "s1",
            "name": "scrubbed_tool",
            "arguments": "{}",
        }
    ]
    assert [r.name for r in retell.normalize(payload)] == ["scrubbed_tool"]


def test_retell_ready_only_when_transcript_present() -> None:
    assert retell.is_ready(RETELL_PAYLOAD) is True
    assert retell.is_ready({"call_id": "x"}) is False
    # An ended call with no tools at all is still a finished record.
    assert retell.is_ready({"call_status": "ended"}) is True


def test_vapi_reads_timing_and_infers_error() -> None:
    records = vapi.normalize(VAPI_PAYLOAD)
    assert len(records) == 1
    call = records[0]
    assert call.name == "search_patient"
    assert call.arguments == {"full_name": "Max"}
    assert call.at_seconds == 9.858
    assert call.turn_index == 2
    # Vapi has no success flag; "No result returned." is its failure marker.
    assert call.status == "error"


def test_vapi_reads_artifact_messages_fallback() -> None:
    payload = {"artifact": {"messages": VAPI_PAYLOAD["messages"]}}
    assert vapi.is_ready(payload) is True
    assert [r.name for r in vapi.normalize(payload)] == ["search_patient"]


def test_elevenlabs_uses_turn_position_and_error_flag() -> None:
    records = elevenlabs.normalize(ELEVEN_PAYLOAD)
    assert len(records) == 1
    call = records[0]
    assert call.name == "check_availability"
    assert call.arguments == {"date": "2026-08-14"}
    assert call.status == "ok"
    assert call.turn_index == 1
    assert call.at_seconds == 7.0
    assert call.result_summary == "3 slots open"


def test_elevenlabs_not_ready_while_processing() -> None:
    assert elevenlabs.is_ready(ELEVEN_PAYLOAD) is True
    assert elevenlabs.is_ready({"transcript": [], "status": "processing"}) is False


def test_retell_missing_success_flag_is_unknown_not_failure() -> None:
    """Retell omits `successful` when nothing was stated — that is not an error."""
    payload = {
        "transcript_with_tool_calls": [
            {
                "role": "tool_call_invocation",
                "tool_call_id": "c1",
                "name": "check_current_date",
                "arguments": "{}",
            },
            {"role": "tool_call_result", "tool_call_id": "c1", "content": "2026-08-13"},
        ]
    }

    assert retell.normalize(payload)[0].status == "unknown"


def test_normalizers_tolerate_junk() -> None:
    for module in (retell, vapi, elevenlabs):
        assert module.normalize({}) == []
        assert module.is_ready({}) is False
        assert module.normalize({"transcript": "nonsense", "messages": 5}) == []


def test_tool_diff_reports_missing_and_unexpected() -> None:
    records = retell.normalize(RETELL_PAYLOAD)

    missing, unexpected = tool_diff(
        ["extract_update_dynamic_variable", "check_current_date"], records
    )

    assert missing == ["check_current_date"]
    assert unexpected == ["transfer_call"]
