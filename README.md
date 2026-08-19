<p align="center">
  <img src="docs/brand/logo-wordmark.png" alt="Wiretap" width="280">
</p>

# Wiretap

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Docs](https://img.shields.io/badge/docs-setup-blue.svg)](docs/setup.md)

**Website:** [wiretap-website.vercel.app](https://wiretap-website.vercel.app/)

[![Wiretap demo](docs/demo.gif)](https://youtu.be/-lqZwtQXGls)

Wiretap is a local-first test harness for voice agents. It pretends to be the caller, dials your **live** agent (Vapi, Retell, ElevenLabs, LiveKit, Synthflow, or phone), and scores the call — rules plus an LLM judge. Results stay in `~/.wiretap/`.

```text
   ┌─────────────┐         dial          ┌──────────────────┐
   │   WIRETAP   │ ───────────────────▶  │ Your live agent  │
   │  test agent │   web / phone / text  │  (Retell, Vapi…) │
   │  + judge    │ ◀───────────────────  │                  │
   └─────────────┘         reply         └──────────────────┘
```

---

## Setup

**Need:** Python ≥ 3.11, [uv](https://docs.astral.sh/uv/), an LLM key (OpenAI or Anthropic), a speech key (PyAI by default), and a platform key if you are dialing a live agent.

```bash
git clone https://github.com/mohibsaas/wiretap.git
cd wiretap
uv sync
uv tool install --editable .

wiretap init                 # test agent → live agent → suite → optional phone
wiretap simulate -s <suite> --all
wiretap report
```

`wiretap init` writes secrets to `~/.wiretap/.env` only — never into suite YAML. Confirm config without printing keys:

```bash
wiretap status
```

> [!TIP]
> Prefer `uv tool install --editable .` so `wiretap` is on your PATH. `uv run wiretap …` works without installing.

Never used a terminal? Use the step-by-step in [docs/setup.md](docs/setup.md).

### Already have keys

```bash
# Put keys in ~/.wiretap/.env — see .env.example
wiretap import retell --agent-id agent_xxx
wiretap simulate --suite retell_agent_xxx --all
wiretap report
```

### Local UI

```bash
cd ui && npm install && npm run build && cd ..
wiretap ui run
# → http://127.0.0.1:8787
```

Dev (hot reload): `uv run wiretap ui run --no-open` then `cd ui && npm install && npm run dev`.

### Optional extras

```bash
uv sync --extra pstn   # real phone calls via Twilio
uv sync --extra mcp    # MCP server for coding agents
uv sync --extra dev    # pytest + ruff
```

Phone vs web is per run (`--transport phone`). Twilio credentials come from `wiretap init` or `~/.wiretap/.env`.

MCP (Cursor example `.cursor/mcp.json`):

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
| `wiretap import …` | Pull a platform agent and generate category tests |
| `wiretap suite …` | list / show / categories / generate |
| `wiretap simulate` | Dial (`--all` or `--scenario`, `--transport web\|phone`) |
| `wiretap report` | Summarize local simulation artifacts |
| `wiretap export` | Copy a suite out for git or sharing |
| `wiretap ui run` | Local dashboard |
| `wiretap status` | What’s configured (no secret values) |

---

## Platforms

| Platform | Live dial | Keys |
| --- | --- | --- |
| Vapi | WebSocket | `VAPI_API_KEY` |
| Retell | LiveKit | `RETELL_API_KEY` |
| ElevenLabs Agents | ConvAI WS | `ELEVENLABS_API_KEY` |
| LiveKit Agents | LiveKit room | `LIVEKIT_API_KEY` + `LIVEKIT_API_SECRET` |
| Synthflow | WS media | `SYNTHFLOW_API_KEY` + from/to numbers |
| Bland / Bolna | Import only | Dial with `--transport phone` |
| Custom / stub | Text | `platform: null`, `transport: text` |
| Phone / PSTN | Twilio SIP | `uv sync --extra pstn` |

Secrets belong in `~/.wiretap/.env` or the environment. Suite YAML stores agent ids and `token_env` **names**, never key values. See [`.env.example`](.env.example).

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

Scoring: **rules** (hard constraints) + **LLM judge** (goal match). Suggestions appear on failures. Categories for generation: `emotional`, `linguistic`, `adversarial`, `operational`, `factual`, `compliance`, `task`, `other`.

More: [docs/](docs/README.md) · [HLD](docs/HLD.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md)
