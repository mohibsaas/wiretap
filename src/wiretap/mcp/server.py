"""MCP server — expose wiretap tools to coding agents."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit(
            "MCP extra not installed. Install with: uv sync --extra mcp"
        ) from exc

    from wiretap.suite import load_suite
    from wiretap.importers import import_vapi_assistant
    from wiretap.paths import suite_path, suites_dir
    from wiretap.agent import simulate_scenario
    from wiretap.suite import iter_simulations

    mcp = FastMCP("wiretap")

    @mcp.tool()
    def list_suites() -> str:
        """List local suite names under .wiretap/suites/."""
        d = suites_dir()
        if not d.is_dir():
            return "[]"
        names = sorted(p.stem for p in d.glob("*.yaml")) + sorted(
            p.stem for p in d.glob("*.yml")
        )
        return json.dumps(names)

    @mcp.tool()
    def simulate_suite(suite: str = "default", scenario: str | None = None) -> str:
        """Simulate a suite (or one scenario) and return JSON results."""

        async def _simulate():
            cfg = load_suite(suite_path(suite))
            selected = cfg.scenarios
            if scenario:
                selected = [s for s in cfg.scenarios if s.id == scenario]
            arts = []
            for sc in selected:
                arts.append(
                    await simulate_scenario(cfg, sc, suite_id=Path(suite).stem)
                )
            return [a.model_dump(mode="json") for a in arts]

        return json.dumps(asyncio.run(_simulate()), indent=2)

    @mcp.tool()
    def latest_simulations(limit: int = 10) -> str:
        """Return recent simulation artifacts as JSON."""
        sims = iter_simulations(limit=limit)
        return json.dumps([r.model_dump(mode="json") for r in sims], indent=2)

    @mcp.tool()
    def import_vapi(assistant_id: str, name: str = "vapi") -> str:
        """Import a Vapi assistant into a local suite."""
        from wiretap.cli.import_cmd import _save_import

        suite, graph = asyncio.run(import_vapi_assistant(assistant_id))
        _save_import(name, suite, graph)
        return f"imported {name}"

    mcp.run()


if __name__ == "__main__":
    main()
