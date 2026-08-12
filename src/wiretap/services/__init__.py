"""Shared service layer for CLI, MCP, and local UI API."""

from wiretap.services.batches import BatchRecord, get_batch, start_batch
from wiretap.services.generator import (
    DEFAULT_CATEGORIES,
    fill_suite_scenarios,
    generate_suite,
    list_categories,
    parse_categories,
)
from wiretap.services.onboard import (
    connect_agent,
    generate_onboard_suite,
    list_agents,
    onboard_status,
)
from wiretap.services.secrets import key_status, upsert_secrets
from wiretap.services.simulations import get_simulation_detail, list_simulations
from wiretap.services.suites import get_suite, list_suites, suite_public_dict

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
