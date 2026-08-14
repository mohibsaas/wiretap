# wiretap

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Test your **live** voice agent from the terminal (or a local UI).

Wiretap dials the agent you already run — Retell, Vapi, ElevenLabs, LiveKit, Synthflow, or a phone number — with its own **test agent**, scores the call (rules + LLM judge), and stores results under `~/.wiretap/` (override with `WIRETAP_HOME`).

```text
   ┌─────────────┐         dial          ┌──────────────────┐
   │   WIRETAP   │ ───────────────────▶  │ Your live agent  │
   │  test agent │   web / phone / text  │  (Retell, Vapi…) │
   │  + judge    │ ◀───────────────────  │                  │
   └─────────────┘         reply         └──────────────────┘
```

---

## Quick start

**Requirements:** Python ≥3.11, [uv](https://docs.astral.sh/uv/), and API keys for an LLM plus speech (STT/TTS). A platform key (e.g. Retell / Vapi) is needed to dial a live agent.

```bash
git clone https://github.com/mohibsaas/wiretap.git
cd wiretap
uv sync
uv tool install --editable .

wiretap init                 # test agent → live agent → suite → optional phone
wiretap simulate -s <suite> --all
wiretap report
```

`wiretap init` writes secrets to `~/.wiretap/.env` only (never into suite YAML). Check config without leaking keys:

```bash
wiretap status
```

> **Tip:** Prefer `uv tool install --editable .` so `wiretap` is on your PATH. `uv run wiretap …` works without installing.

### Minimal path (already have keys)

```bash
# Put keys in ~/.wiretap/.env — see .env.example
wiretap import retell --agent-id agent_xxx
wiretap simulate --suite retell_agent_xxx --all
wiretap report
```

---

## Local UI

```bash
cd ui && npm install && npm run build && cd ..
wiretap ui run
# → http://127.0.0.1:8787
```

Same `~/.wiretap/` data and onboarding as the CLI. For UI development (hot reload):

```bash
uv run wiretap ui run --no-open          # API on :8787
cd ui && npm install && npm run dev      # Vite proxies /api
```

---

## Optional extras

```bash
uv sync --extra pstn   # real phone calls via Twilio
uv sync --extra mcp    # MCP server for coding agents
uv sync --extra dev    # pytest + ruff
```

**Phone:** web vs phone is a per-run choice (`--transport phone`). Needs Twilio credentials from `wiretap init` (or `.env`).

**MCP:**

```bash
uv sync --extra mcp
uv run wiretap-mcp
```

Cursor example (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "wiretap": { "command": "uv", "args": ["run", "wiretap-mcp"] }
  }
}
```

---

## Commands

| Command | What it does |
| --- | --- |
| `wiretap init` | First-run setup (simulator → agent → suite → phone) |
| `wiretap import …` | Pull a platform agent + generate category tests |
| `wiretap suite …` | list / show / categories / generate |
| `wiretap simulate` | Dial (`--all` or `--scenario`, `--transport web\|phone`) |
| `wiretap report` | Summarize local simulation artifacts |
| `wiretap export` | Copy a suite out for git or sharing |
| `wiretap ui run` | Local dashboard |
| `wiretap status` | What’s configured (no secret values) |

---

## Platforms

| Platform | Live dial | Notes |
| --- | --- | --- |
| Vapi | WebSocket | `VAPI_API_KEY` |
| Retell | LiveKit | `RETELL_API_KEY` |
| ElevenLabs Agents | ConvAI WS | `ELEVENLABS_API_KEY` |
| LiveKit Agents | LiveKit room | `LIVEKIT_API_KEY` + `LIVEKIT_API_SECRET` |
| Synthflow | WS media | `SYNTHFLOW_API_KEY` + from/to numbers |
| Bland / Bolna | Import only | Dial via `--transport phone` |
| Custom / stub | Text | `platform: null`, `transport: text` |
| Phone / PSTN | Twilio SIP | `uv sync --extra pstn` |

Secrets belong in `~/.wiretap/.env` or the environment. Suite YAML stores agent ids and `token_env` **names**, never key values. See [`.env.example`](.env.example).

---

## How scoring works

- **Rules** check hard constraints from the suite.
- **LLM judge** scores goal match (pass / partial / fail).
- **Suggestions** appear on failures only.
- Optional **advisor** can suggest config fixes after failing calls.

Test categories used for generation: `emotional`, `linguistic`, `adversarial`, `operational`, `factual`, `compliance`, `task`, `other`.

---

## Data layout

```text
~/.wiretap/          # or $WIRETAP_HOME
  .env               # secrets (from wiretap init)
  suites/            # YAML suites
  simulations/       # call artifacts + transcripts
  evaluations/       # run summaries + live progress
  onboard.json
```

Architecture notes: [docs/HLD.md](docs/HLD.md).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).

Security reports: [SECURITY.md](SECURITY.md) — please use private disclosure, not public issues.

```bash
uv sync --extra dev
uv run ruff check src tests
uv run pytest -q
```

## License

[MIT](LICENSE)
