"""Live prompt preview/apply — draft compose, hash guard, finding allowlist."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from wiretap.models import (
    AdviceEvidence,
    AdviceFinding,
    AgentTarget,
    RunAdvice,
    SuiteConfig,
)
from wiretap.services.prompt_apply import (
    LivePrompt,
    PromptApplyError,
    apply_prompt,
    compose_draft,
    filter_new_additions,
    platform_writable,
    preview_prompt,
    prompt_diff,
    prompt_hash,
    select_additions,
)


def _advice(*findings: AdviceFinding) -> RunAdvice:
    return RunAdvice(summary="x", findings=list(findings), grounding="config")


def _prompt_finding(fid: str, text: str, target: str = "agent_prompt") -> AdviceFinding:
    return AdviceFinding(
        id=fid,
        target=target,
        title=fid,
        suggested_text=text,
        evidence=[AdviceEvidence(scenario_id="a", quote="said something")],
    )


def _suite(platform: str = "retell", agent_id: str = "ag1") -> SuiteConfig:
    return SuiteConfig(
        agent=AgentTarget(platform=platform, agent_id=agent_id, token_env="RETELL_API_KEY"),
        personas=[],
        scenarios=[],
    )


def test_compose_draft_appends_in_order() -> None:
    draft = compose_draft("You are a booking agent.", ["Verify identity.", "Confirm callbacks."])
    assert draft.startswith("You are a booking agent.")
    assert draft.endswith("Confirm callbacks.")
    assert "Verify identity." in draft


def test_compose_draft_empty_current() -> None:
    assert compose_draft("", ["Only addition"]) == "Only addition"


def test_filter_skips_wording_already_in_prompt() -> None:
    current = (
        "You are a booking agent.\n"
        "Always verify the caller's identity before quoting a price."
    )
    new, skipped = filter_new_additions(
        current,
        [
            ("dup", "Always verify the caller's identity before quoting a price."),
            ("fresh", "Confirm the callback number before hanging up."),
        ],
    )
    assert [fid for fid, _ in new] == ["fresh"]
    assert skipped[0]["id"] == "dup"
    assert skipped[0]["reason"] == "already_in_prompt"


def test_filter_skips_sentence_already_covered() -> None:
    current = "Never share the OTP. Always read the address back to the caller."
    new, skipped = filter_new_additions(
        current,
        [("p1", "Always read the address back to the caller.")],
    )
    assert new == []
    assert skipped[0]["reason"] == "already_in_prompt"


def test_filter_skips_duplicate_selection() -> None:
    current = "You book cleanings."
    new, skipped = filter_new_additions(
        current,
        [
            ("a", "Ask for the ZIP code twice."),
            ("b", "Ask for the ZIP code twice."),
        ],
    )
    assert [fid for fid, _ in new] == ["a"]
    assert skipped[0]["id"] == "b"
    assert skipped[0]["reason"] == "already_in_selection"


def test_prompt_diff_marks_appended_lines() -> None:
    hunks = prompt_diff("You are a booking agent.", "You are a booking agent.\n\nConfirm callbacks.")
    ops = [(h["op"], h["text"]) for h in hunks]
    assert any(op == "equal" and "booking agent" in text for op, text in ops)
    assert any(op == "insert" and "Confirm callbacks." in text for op, text in ops)
    assert all(op != "delete" or not text.strip() for op, text in ops)


def test_select_additions_skips_non_prompt_and_unknown() -> None:
    advice = _advice(
        _prompt_finding("a", "Add A"),
        _prompt_finding("b", "Add B", target="tools"),
        _prompt_finding("c", "Add C"),
    )
    picked = select_additions(advice, ["missing", "b", "c", "a", "a"])
    assert [fid for fid, _ in picked] == ["c", "a"]


def test_platform_writable() -> None:
    assert platform_writable("retell")
    assert platform_writable("Vapi")
    assert not platform_writable("livekit")
    assert not platform_writable(None)


def test_preview_and_apply_hash_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    live = LivePrompt(platform="retell", agent_id="ag1", current="Hello.", extra={"llm_id": "llm1"})
    written: list[str] = []

    async def _get(suite: SuiteConfig) -> LivePrompt:
        return live

    async def _write(suite: SuiteConfig, *, draft: str, live: LivePrompt) -> None:
        written.append(draft)

    monkeypatch.setattr("wiretap.services.prompt_apply.fetch_live_prompt", _get)
    monkeypatch.setattr("wiretap.services.prompt_apply.write_live_prompt", _write)

    advice = _advice(_prompt_finding("p1", "Always verify."))
    suite = _suite()
    preview = asyncio.run(preview_prompt(suite, advice, ["p1"]))
    assert preview["current"] == "Hello."
    assert preview["additions"] == ["Always verify."]
    assert preview["skipped"] == []
    assert preview["unchanged"] is False
    assert "Always verify." in preview["draft"]
    assert any(h["op"] == "insert" and "Always verify." in h["text"] for h in preview["diff"])
    assert preview["current_hash"] == prompt_hash("Hello.")

    live.current = "Changed underneath."
    with pytest.raises(PromptApplyError) as mismatch:
        asyncio.run(
            apply_prompt(
                suite, advice, ["p1"], current_hash=preview["current_hash"]
            )
        )
    assert mismatch.value.code == "prompt_changed"
    assert mismatch.value.status == 409
    assert written == []

    live.current = "Hello."
    result = asyncio.run(
        apply_prompt(suite, advice, ["p1"], current_hash=preview["current_hash"])
    )
    assert result["ok"] is True
    assert written == [preview["draft"]]


def test_preview_and_apply_skip_already_present(monkeypatch: pytest.MonkeyPatch) -> None:
    live = LivePrompt(
        platform="retell",
        agent_id="ag1",
        current="Hello.\nAlways verify.",
        extra={"llm_id": "llm1"},
    )
    written: list[str] = []

    async def _get(suite: SuiteConfig) -> LivePrompt:
        return live

    async def _write(suite: SuiteConfig, *, draft: str, live: LivePrompt) -> None:
        written.append(draft)

    monkeypatch.setattr("wiretap.services.prompt_apply.fetch_live_prompt", _get)
    monkeypatch.setattr("wiretap.services.prompt_apply.write_live_prompt", _write)

    advice = _advice(_prompt_finding("p1", "Always verify."))
    suite = _suite()
    preview = asyncio.run(preview_prompt(suite, advice, ["p1"]))
    assert preview["additions"] == []
    assert preview["unchanged"] is True
    assert preview["applied_finding_ids"] == []
    assert preview["skipped"][0]["reason"] == "already_in_prompt"

    with pytest.raises(PromptApplyError) as exc:
        asyncio.run(
            apply_prompt(
                suite, advice, ["p1"], current_hash=preview["current_hash"]
            )
        )
    assert exc.value.code == "already_present"
    assert written == []


def test_preview_rejects_empty_selection() -> None:
    advice = _advice(_prompt_finding("p1", "Add A"))
    with pytest.raises(PromptApplyError) as exc:
        asyncio.run(preview_prompt(_suite(), advice, ["nope"]))
    assert exc.value.code == "no_findings"


def test_unsupported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "wiretap.services.prompt_apply.require_env", lambda name: "secret"
    )
    with pytest.raises(PromptApplyError) as exc:
        asyncio.run(preview_prompt(_suite(platform="livekit"), _advice(_prompt_finding("p1", "x")), ["p1"]))
    assert exc.value.code == "unsupported_platform"


def test_api_preview_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from wiretap.suite import dump_suite
    from wiretap.suite.evaluations import save_evaluation_run
    from wiretap.ui.app import create_app

    (tmp_path / ".wiretap" / "suites").mkdir(parents=True)
    suite = _suite()
    dump_suite(suite, tmp_path / ".wiretap" / "suites" / "default.yaml")
    save_evaluation_run(
        {
            "batch_id": "batch1",
            "suite_id": "default",
            "advice": _advice(_prompt_finding("p1", "Verify the caller.")).model_dump(
                mode="json"
            ),
        },
        tmp_path,
    )

    live = LivePrompt(platform="retell", agent_id="ag1", current="Base prompt.", extra={})
    written: list[str] = []

    async def _get(cfg: SuiteConfig) -> LivePrompt:
        return live

    async def _write(cfg: SuiteConfig, *, draft: str, live: LivePrompt) -> None:
        written.append(draft)

    monkeypatch.setattr("wiretap.services.prompt_apply.fetch_live_prompt", _get)
    monkeypatch.setattr("wiretap.services.prompt_apply.write_live_prompt", _write)

    client = TestClient(create_app(cwd=tmp_path))
    preview = client.post(
        "/api/evaluations/batch1/prompt-preview",
        json={"finding_ids": ["p1"]},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert "Verify the caller." in body["draft"]
    assert "secret" not in preview.text.lower()

    apply = client.post(
        "/api/evaluations/batch1/prompt-apply",
        json={"finding_ids": ["p1"], "current_hash": body["current_hash"]},
    )
    assert apply.status_code == 200, apply.text
    assert apply.json()["ok"] is True
    assert written == [body["draft"]]
