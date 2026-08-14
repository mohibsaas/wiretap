# Contributing

Thanks for helping improve wiretap.

## Development setup

```bash
git clone https://github.com/mohibsaas/wiretap.git
cd wiretap
uv sync --extra dev
uv tool install --editable .
```

Optional UI work:

```bash
cd ui && npm install && npm run dev   # Vite on :5173, proxies /api → :8787
# terminal 2:
uv run wiretap ui run --no-open
```

Run checks before opening a PR:

```bash
uv run ruff check src tests
uv run pytest -q
```

## Pull requests

- Keep changes focused (one concern per PR when possible).
- Do not commit secrets, `.env`, or `~/.wiretap/` data.
- Prefer `wiretap init` / `.env.example` patterns for any new credentials.
- Update the README when you change install, CLI, or first-run behavior.

## Code style

- Python ≥3.11, formatted/linted with Ruff (`line-length = 100`).
- UI: TypeScript + React in `ui/` (build output ships in `src/wiretap/ui/static/`).

## License

By contributing, you agree that your contributions are licensed under the MIT License.
