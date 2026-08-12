"""Shared service layer for CLI, MCP, and local UI API.

Keep this module light — do not eagerly import onboard/secrets (LiteLLM).
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "BatchRecord",
    "DEFAULT_CATEGORIES",
    "connect_agent",
    "fill_suite_scenarios",
    "generate_onboard_suite",
    "generate_suite",
    "get_batch",
    "get_simulation_detail",
    "get_suite",
    "key_status",
    "list_agents",
    "list_categories",
    "list_simulations",
    "list_suites",
    "onboard_status",
    "parse_categories",
    "start_batch",
    "suite_public_dict",
    "upsert_secrets",
]


def __getattr__(name: str) -> Any:
    if name in {"DEFAULT_CATEGORIES", "fill_suite_scenarios", "generate_suite", "list_categories", "parse_categories"}:
        from wiretap.services import generator as g

        return getattr(g, name)
    if name in {"BatchRecord", "get_batch", "start_batch"}:
        from wiretap.services import batches as b

        return getattr(b, name)
    if name in {
        "connect_agent",
        "generate_onboard_suite",
        "list_agents",
        "onboard_status",
    }:
        from wiretap.services import onboard as o

        return getattr(o, name)
    if name in {"key_status", "upsert_secrets"}:
        from wiretap.services import secrets as s

        return getattr(s, name)
    if name in {"get_simulation_detail", "list_simulations"}:
        from wiretap.services import simulations as sim

        return getattr(sim, name)
    if name in {"get_suite", "list_suites", "suite_public_dict"}:
        from wiretap.services import suites as su

        return getattr(su, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
