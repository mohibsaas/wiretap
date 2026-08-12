"""suite list | show | path | generate | categories."""

from __future__ import annotations

import typer
from rich import print

from wiretap.paths import ensure_layout, suite_path, suites_dir
from wiretap.services.generator import (
    DEFAULT_CATEGORIES,
    fill_suite_scenarios,
    list_categories,
    parse_categories,
)
from wiretap.suite import dump_suite, load_suite

_CAT_HELP = (
    "Comma-separated categories "
    f"(default: {','.join(DEFAULT_CATEGORIES)}). "
    "emotional,linguistic,adversarial,operational,factual,compliance,task,other"
)


def register(app: typer.Typer) -> None:
    suite_app = typer.Typer(
        no_args_is_help=True,
        help="Manage local suites under .wiretap/suites/.",
    )
    app.add_typer(suite_app, name="suite")

    @suite_app.command("list")
    def suite_list() -> None:
        """List local suites."""
        d = suites_dir()
        if not d.is_dir():
            print(
                "No suites yet. Use [bold]wiretap import[/bold] or the UI onboarding."
            )
            raise typer.Exit(0)
        files = sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml"))
        if not files:
            print(
                "No suites yet. Use [bold]wiretap import[/bold] or the UI onboarding."
            )
            raise typer.Exit(0)
        for f in files:
            print(f.stem)

    @suite_app.command("path")
    def suite_path_cmd(name: str = typer.Argument("default")) -> None:
        """Print the filesystem path for a suite."""
        print(suite_path(name))

    @suite_app.command("show")
    def suite_show(name: str = typer.Argument("default")) -> None:
        """Print suite YAML."""
        path = suite_path(name)
        if not path.is_file():
            print(f"[red]Not found:[/red] {path}")
            raise typer.Exit(1)
        print(path.read_text(encoding="utf-8"))

    @suite_app.command("categories")
    def suite_categories() -> None:
        """List available test categories."""
        for c in list_categories():
            print(
                f"[bold]{c['id']}[/bold]  {c['label']} — {c['description']} "
                f"(up to {c['max_tests']})"
            )

    @suite_app.command("generate")
    def suite_generate(
        suite: str = typer.Option(..., "--suite", "-s", help="Existing suite name to refill."),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(5, "--tests-per-category", "-n", min=1, max=10),
        purpose: str = typer.Option("", "--purpose", "-p", help="Optional purpose context."),
    ) -> None:
        """Regenerate scenarios for an existing suite from category templates."""
        path = suite_path(suite)
        if not path.is_file():
            print(f"[red]Not found:[/red] {path}")
            print("Import an agent first, or create a suite YAML under .wiretap/suites/.")
            raise typer.Exit(1)
        cfg = load_suite(path)
        cats = parse_categories(categories)
        fill_suite_scenarios(
            cfg,
            categories=cats,
            tests_per_category=tests_per_category,
            purpose=purpose,
            agent_name=str(cfg.agent.agent_id or cfg.agent.platform or suite),
        )
        ensure_layout()
        dump_suite(cfg, path)
        by_cat: dict[str, int] = {}
        for s in cfg.scenarios:
            key = s.category or "untagged"
            by_cat[key] = by_cat.get(key, 0) + 1
        print(f"[green]Updated[/green] {path}")
        print(f"Scenarios: {len(cfg.scenarios)} ({by_cat})")
