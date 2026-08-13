"""Transcript selection for judging."""

from __future__ import annotations

from wiretap.models import TurnRecord
from wiretap.transport.transcript_util import (
    pick_judge_transcript,
    transcript_fragment_score,
)


def test_prefer_live_when_provider_misses_user() -> None:
    live = [
        TurnRecord(role="agent", text="Hello?"),
        TurnRecord(role="user", text="Hi there, I need help."),
    ]
    official = [
        TurnRecord(role="agent", text="Hello?"),
        TurnRecord(role="agent", text="Are you still there?"),
    ]
    chosen, source = pick_judge_transcript(live, official)
    assert source == "live_provider_missed_user"
    assert chosen is live


def test_prefer_live_when_provider_more_fragmented() -> None:
    live = [
        TurnRecord(role="agent", text="Thanks for calling Sam The Concrete Man. How can I help?"),
        TurnRecord(role="user", text="I need a patio estimate."),
    ]
    official = [
        TurnRecord(role="agent", text="Thanks for"),
        TurnRecord(role="user", text="I need"),
        TurnRecord(role="agent", text="calling"),
        TurnRecord(role="user", text="a patio"),
        TurnRecord(role="agent", text="Sam The"),
    ]
    assert transcript_fragment_score(official) > transcript_fragment_score(live)
    chosen, source = pick_judge_transcript(live, official)
    assert source == "live_less_fragmented"
    assert chosen is live


def test_prefer_provider_when_coherent() -> None:
    live = [
        TurnRecord(role="agent", text="Hi"),
        TurnRecord(role="user", text="Hello"),
    ]
    official = [
        TurnRecord(
            role="agent",
            text="Hi, thanks for calling. How can I help you today?",
        ),
        TurnRecord(role="user", text="Hello, I need a quote for a patio."),
    ]
    chosen, source = pick_judge_transcript(live, official)
    assert source == "provider_final"
    assert chosen is official
