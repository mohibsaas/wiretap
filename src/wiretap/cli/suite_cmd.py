"""suite list | show | path | generate | categories."""

from __future__ import annotations

import sys

import typer
from rich import print
from rich.table import Table

from wiretap.services.generator import DEFAULT_CATEGORIES

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
        from wiretap.paths import suites_dir

        d = suites_dir()
        if not d.is_dir():
            print(
                "No suites yet. Use [bold]wiretap import[/bold], "
                "[bold]wiretap suite generate[/bold], or the UI onboarding."
            )
            raise typer.Exit(0)
        files = sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml"))
        if not files:
            print(
                "No suites yet. Use [bold]wiretap import[/bold], "
                "[bold]wiretap suite generate[/bold], or the UI onboarding."
            )
            raise typer.Exit(0)
        for f in files:
            print(f.stem)

    @suite_app.command("path")
    def suite_path_cmd(name: str = typer.Argument("default")) -> None:
        """Print the filesystem path for a suite."""
        from wiretap.paths import suite_path

        print(suite_path(name))

    @suite_app.command("show")
    def suite_show(name: str = typer.Argument("default")) -> None:
        """Print suite YAML."""
        from wiretap.paths import suite_path

        path = suite_path(name)
        if not path.is_file():
            print(f"[red]Not found:[/red] {path}")
            raise typer.Exit(1)
        print(path.read_text(encoding="utf-8"))

    @suite_app.command("categories")
    def suite_categories() -> None:
        """List available test categories."""
        from wiretap.services.generator import list_categories

        for c in list_categories():
            print(
                f"[bold]{c['id']}[/bold]  {c['label']} — {c['description']} "
                f"(up to {c['max_tests']})"
            )

    @suite_app.command("generate")
    def suite_generate(
        suite: str = typer.Option(
            ...,
            "--suite",
            "-s",
            help="Suite name (created if missing; spaces become underscores).",
        ),
        categories: str = typer.Option(
            ",".join(DEFAULT_CATEGORIES), "--categories", "-C", help=_CAT_HELP
        ),
        tests_per_category: int = typer.Option(
            5, "--tests-per-category", "-n", min=1, max=10
        ),
        purpose: str = typer.Option(
            "",
            "--purpose",
            "-p",
            help="What the agent does (enough to create a new suite).",
        ),
        agent_from: str | None = typer.Option(
            None,
            "--agent-from",
            help="Bind agent target from an imported suite (live dials use that agent).",
        ),
    ) -> None:
        """Create or refill a suite via LLM (category-guided).

        New suite: pass --purpose and/or --agent-from.
        Existing suite: regenerates scenarios; keeps the current agent target.

        When the agent was imported, generation is grounded in a sanitized brief
        of its prompt, tools and flow read from .wiretap/graphs/. Otherwise it
        falls back to --purpose plus category guidance.
        """
        from wiretap.importers.suite_builder import slug
        from wiretap.paths import ensure_layout, suite_path
        from wiretap.services.agent_brief import brief_for_suite
        from wiretap.services.generator import fill_suite_scenarios, parse_categories
        from wiretap.services.onboard import load_onboard_state
        from wiretap.suite import dump_suite, load_suite

        name = slug(suite)
        if not name:
            print("[red]Invalid suite name[/red]")
            raise typer.Exit(1)
        if name != suite.strip():
            print(f"[dim]Suite id[/dim] {name}  (from {suite!r})")

        path = suite_path(name)
        cats = parse_categories(categories)
        purpose_bit = (purpose or "").strip()
        agent_from_bit = (agent_from or "").strip() or None

        # Interactive resolve when creating and neither purpose nor agent-from given
        if not path.is_file() and not purpose_bit and not agent_from_bit:
            purpose_bit, agent_from_bit = _prompt_create_inputs()

        if path.is_file():
            cfg = load_suite(path)
            if agent_from_bit:
                cfg = _apply_agent_from(cfg, agent_from_bit)
            agent_label = str(cfg.agent.agent_id or cfg.agent.platform or name)
            # The imported agent config lives beside the suite as graph IR.
            # --agent-from rebinds the target, so prefer that agent's graph.
            brief = brief_for_suite(
                agent_from_bit or name,
                suite=cfg,
                purpose=purpose_bit,
                agent_name=agent_label,
            )
            print(
                f"[cyan]Refilling[/cyan] {path.name}  "
                f"[dim]agent[/dim] {agent_label}  "
                f"[dim]model[/dim] {cfg.models.simulator}"
                + ("  [dim]grounded in agent config[/dim]" if brief else "")
            )
            fill_suite_scenarios(
                cfg,
                categories=cats,
                tests_per_category=tests_per_category,
                purpose=purpose_bit,
                agent_name=agent_label,
                model=cfg.models.simulator,
                brief=brief,
            )
            action = "Updated"
        else:
            if not purpose_bit and not agent_from_bit:
                print(
                    "[red]New suite needs[/red] [bold]--purpose[/bold] "
                    "(what the agent does) and/or [bold]--agent-from[/bold] "
                    "(an imported suite)."
                )
                print(
                    "Examples:\n"
                    '  wiretap suite generate -s booking -C task -p "Appointment booking bot"\n'
                    "  wiretap suite generate -s booking -C task --agent-from retell_agent_xxx"
                )
                _print_agent_table()
                raise typer.Exit(1)

            cfg = _build_new_suite(
                name=name,
                purpose=purpose_bit,
                agent_from=agent_from_bit,
                categories=cats,
                tests_per_category=tests_per_category,
            )
            # Prefer onboard speech/models when available
            state = load_onboard_state()
            if state.get("simulator_model"):
                cfg.models.simulator = str(state["simulator_model"])
            if state.get("judge_model"):
                cfg.models.judge = str(state["judge_model"])
            if state.get("stt"):
                cfg.speech.stt = str(state["stt"])
            if state.get("tts"):
                cfg.speech.tts = str(state["tts"])
            if state.get("voice"):
                cfg.speech.voice = str(state["voice"])

            agent_label = str(cfg.agent.agent_id or cfg.agent.platform or "custom")
            print(
                f"[cyan]Creating[/cyan] {path.name}  "
                f"[dim]agent[/dim] {agent_label}  "
                f"[dim]model[/dim] {cfg.models.simulator}"
            )
            # Scenarios already generated in _build_new_suite when purpose given;
            # if only agent-from, generate now with imported prompt context
            if not cfg.scenarios:
                fill_suite_scenarios(
                    cfg,
                    categories=cats,
                    tests_per_category=tests_per_category,
                    purpose=purpose_bit,
                    agent_name=agent_label,
                    model=cfg.models.simulator,
                    brief=brief_for_suite(
                        agent_from_bit or name,
                        suite=cfg,
                        purpose=purpose_bit,
                        agent_name=agent_label,
                    ),
                )
            action = "Created"

        ensure_layout()
        dump_suite(cfg, path)
        by_cat: dict[str, int] = {}
        for s in cfg.scenarios:
            key = s.category or "untagged"
            by_cat[key] = by_cat.get(key, 0) + 1
        print(f"[green]{action}[/green] {path}")
        print(f"Scenarios: {len(cfg.scenarios)} ({by_cat})")
        if cfg.agent.platform is None:
            print(
                "[dim]Stub agent (text). To dial a live agent later:[/dim]\n"
                f"  wiretap simulate -s {name} --all --agent-from <imported_suite>"
            )


def _prompt_create_inputs() -> tuple[str, str | None]:
    """Ask for purpose and/or imported agent when creating interactively."""
    if not sys.stdin.isatty():
        return "", None

    agents = _agent_choices()
    agent_from: str | None = None
    if agents:
        _print_agent_table(agents)
        raw = typer.prompt(
            "Bind imported agent suite (name), or press Enter to skip",
            default="",
            show_default=False,
        ).strip()
        if raw:
            # Accept suite name or agent id
            match = next(
                (
                    a
                    for a in agents
                    if a["suite"] == raw or a.get("agent_id") == raw or a.get("id") == raw
                ),
                None,
            )
            if match and match.get("suite"):
                agent_from = str(match["suite"])
            elif any(a.get("suite") == raw for a in agents):
                agent_from = raw
            else:
                print(f"[yellow]Unknown agent {raw!r} — continuing without bind[/yellow]")

    purpose = typer.prompt(
        "Purpose (what should these tests cover?)"
        + (" — optional if agent bound" if agent_from else ""),
        default="" if agent_from else None,
    )
    return str(purpose or "").strip(), agent_from


def _agent_choices() -> list[dict]:
    from wiretap.services.onboard import list_agents

    return [a for a in list_agents() if a.get("suite") and a.get("platform")]


def _print_agent_table(agents: list[dict] | None = None) -> None:
    rows = agents if agents is not None else _agent_choices()
    if not rows:
        print("[dim]No imported live agents yet. Use wiretap import … first.[/dim]")
        return
    table = Table(title="Imported agents", show_header=True, header_style="bold")
    table.add_column("Suite")
    table.add_column("Platform")
    table.add_column("Agent id")
    for a in rows:
        table.add_row(
            str(a.get("suite") or ""),
            str(a.get("platform") or ""),
            str(a.get("agent_id") or a.get("id") or ""),
        )
    print(table)


def _apply_agent_from(cfg, agent_from: str):
    from wiretap.paths import suite_path
    from wiretap.suite.agent_override import with_agent_override

    src = suite_path(agent_from)
    if not src.is_file():
        print(f"[red]--agent-from not found:[/red] {src}")
        raise typer.Exit(1)
    return with_agent_override(cfg, agent_from=agent_from)


def _build_new_suite(
    *,
    name: str,
    purpose: str,
    agent_from: str | None,
    categories: list[str],
    tests_per_category: int,
):
    from wiretap.paths import suite_path
    from wiretap.services.agent_brief import brief_for_suite
    from wiretap.services.generator import generate_suite
    from wiretap.suite import load_suite

    platform = "custom"
    agent_id = None
    transport = "text"
    agent_name = name
    room_url = None
    token_env = None
    models_sim = "gpt-4o-mini"
    brief: dict = {}

    if agent_from:
        src_path = suite_path(agent_from)
        if not src_path.is_file():
            print(f"[red]--agent-from not found:[/red] {src_path}")
            raise typer.Exit(1)
        src = load_suite(src_path)
        platform = src.agent.platform or "custom"
        agent_id = src.agent.agent_id
        transport = src.agent.transport.value
        room_url = src.agent.room_url
        token_env = src.agent.token_env
        agent_name = str(agent_id or platform or name)
        models_sim = src.models.simulator
        brief = brief_for_suite(
            agent_from,
            suite=src,
            purpose=purpose,
            agent_name=agent_name,
        )
        if brief:
            print("[dim]Grounding tests in the imported agent config[/dim]")

    purpose_for_llm = purpose or (
        f"Tests for {agent_name}" if agent_from else ""
    )
    suite = generate_suite(
        platform=platform,
        agent_id=agent_id,
        agent_name=agent_name,
        purpose=purpose_for_llm,
        categories=categories,
        tests_per_category=tests_per_category,
        transport=transport,
        model=models_sim,
        brief=brief,
    )
    if room_url:
        suite.agent.room_url = room_url
    if token_env:
        suite.agent.token_env = token_env
    return suite
