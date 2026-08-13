"""Generation progress callback events."""

from __future__ import annotations

from wiretap.services.generator import generate_suite


def test_generate_suite_emits_progress(monkeypatch) -> None:
    events: list[dict] = []

    def fake_llm(**kwargs):
        cat = kwargs["category"]
        n = kwargs["count"]
        return [
            {
                "name": f"{cat}-{i}",
                "identity": f"Caller {i}",
                "goal": "Do the thing",
                "say": "Hello",
                "success": "Done",
                "excludes": [],
            }
            for i in range(n)
        ]

    monkeypatch.setattr(
        "wiretap.services.generator.llm_generate_category_tests",
        fake_llm,
    )

    suite = generate_suite(
        platform="custom",
        agent_id=None,
        agent_name="demo",
        purpose="Demo",
        categories=["task", "compliance"],
        tests_per_category=3,
        transport="text",
        on_progress=events.append,
    )
    assert len(suite.scenarios) == 6
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "start"
    assert kinds[-1] == "done"
    assert events[0]["total"] == 6
    assert events[-1]["done"] == 6
    assert any(e["kind"] == "category_start" and e["category"] == "task" for e in events)
    assert any(e["kind"] == "category_done" and e["done"] == 3 for e in events)
    assert any(e["kind"] == "category_done" and e["done"] == 6 for e in events)
