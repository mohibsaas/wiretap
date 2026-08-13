"""Provider utterance timing extraction."""

from __future__ import annotations

from wiretap.transport.transcript_util import utterance_timing_ms


def test_utterance_timing_from_retell_words() -> None:
    start, end = utterance_timing_ms(
        {
            "role": "agent",
            "content": "hi how are you",
            "words": [
                {"word": "hi", "start": 0.7, "end": 1.0},
                {"word": "how", "start": 1.0, "end": 1.2},
                {"word": "are", "start": 1.2, "end": 1.4},
                {"word": "you", "start": 1.4, "end": 1.8},
            ],
        }
    )
    assert start == 700.0
    assert end == 1800.0


def test_utterance_timing_missing_words() -> None:
    assert utterance_timing_ms({"role": "user", "content": "hello"}) == (None, None)


def test_utterance_timing_utterance_level_fallback() -> None:
    start, end = utterance_timing_ms(
        {"role": "agent", "content": "hi", "start": 2.5, "end": 4.0}
    )
    assert start == 2500.0
    assert end == 4000.0
