"""Catalog model / voice shortlists for onboarding."""

from __future__ import annotations

from wiretap.providers.catalog import (
    default_voice_for,
    models_for_provider,
    provider_catalog,
    voices_for_tts,
)


def test_models_for_openai_are_curated() -> None:
    models = models_for_provider("openai")
    assert models[0] == "gpt-4o-mini"
    assert "gpt-4o" in models
    assert all("1024-x" not in m for m in models)


def test_default_voice_differs_by_tts() -> None:
    assert default_voice_for("openai") == "alloy"
    assert default_voice_for("pyai") == "alloy"
    assert default_voice_for("elevenlabs") == "21m00Tcm4TlvDq8ikWAM"
    assert default_voice_for("deepgram") == "aura-asteria-en"
    assert default_voice_for("lmnt") == "lily"


def test_voices_for_elevenlabs_include_labels() -> None:
    voices = voices_for_tts("elevenlabs")
    assert any(v["label"] == "Rachel" for v in voices)
    assert all("id" in v and "label" in v for v in voices)


def test_provider_catalog_exposes_models_and_voices() -> None:
    provider_catalog.cache_clear()
    cat = provider_catalog()
    openai = next(p for p in cat["llm"] if p["id"] == "openai")
    assert "gpt-4o-mini" in openai["models"]
    pyai = next(p for p in cat["tts"] if p["id"] == "pyai")
    assert pyai["default_voice"] == "alloy"
    assert any(v["id"] == "alloy" for v in pyai["voices"])
    el = next(p for p in cat["tts"] if p["id"] == "elevenlabs")
    assert el["default_voice"] == "21m00Tcm4TlvDq8ikWAM"
    assert cat["defaults"]["voice"] == default_voice_for(cat["defaults"]["tts"])
