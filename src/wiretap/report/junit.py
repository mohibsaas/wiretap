"""JUnit XML + JSON suite reports for CI."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from wiretap.models import SimulationArtifact


def write_json_report(artifacts: list[SimulationArtifact], path: Path | str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "passed": all(
            a.passed or a.meta.get("inconclusive") for a in artifacts
        ),
        "total": len(artifacts),
        "failures": sum(
            1 for a in artifacts if not a.passed and not a.meta.get("inconclusive")
        ),
        "inconclusive": sum(1 for a in artifacts if a.meta.get("inconclusive")),
        "results": [a.model_dump(mode="json") for a in artifacts],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def write_junit_report(
    artifacts: list[SimulationArtifact],
    path: Path | str,
    *,
    suite_name: str = "wiretap",
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Inconclusive (caller meta-check) → skipped, not failure — matches CLI exit code
    hard_fails = [
        a for a in artifacts if not a.passed and not a.meta.get("inconclusive")
    ]
    skipped = [a for a in artifacts if a.meta.get("inconclusive")]
    root = ET.Element(
        "testsuite",
        name=suite_name,
        tests=str(len(artifacts)),
        failures=str(len(hard_fails)),
        skipped=str(len(skipped)),
        errors="0",
    )
    for art in artifacts:
        case = ET.SubElement(
            root,
            "testcase",
            classname=art.suite_id,
            name=art.scenario_id,
        )
        if art.meta.get("inconclusive"):
            ET.SubElement(case, "skipped", message="simulator_invalid")
        elif not art.passed:
            fail = ET.SubElement(case, "failure", message=art.judge.reason[:200])
            parts = [art.judge.reason, *art.rules.failures, *art.judge.suggestions]
            fail.text = "\n".join(parts)
    tree = ET.ElementTree(root)
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return out


__all__ = ["write_json_report", "write_junit_report"]
