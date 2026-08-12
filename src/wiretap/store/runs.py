"""Deprecated module path — use wiretap.store.simulations."""

from wiretap.store.simulations import (  # noqa: F401
    get_simulation,
    iter_simulations,
    latest_baseline,
    regression_failed,
    save_simulation,
)

# Legacy names
save_run = save_simulation
iter_runs = iter_simulations
