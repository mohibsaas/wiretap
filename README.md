# wiretap

Test your **live** voice agent from the terminal.

Wiretap dials the agent you already run (Vapi, Retell, or a text stub) with its own **test agent**, scores the call with rules + an LLM judge, and stores results under `.wiretap/`.

```text
   ┌─────────────┐         dial          ┌──────────────────┐
   │   WIRETAP   │ ───────────────────▶  │ Your live agent  │
   │             │   Vapi / Retell /     │                  │
   │  test agent │   text                │  (Retell, Vapi,  │
   │  + judge    │ ◀───────────────────  │   custom, …)     │
   └─────────────┘         reply         └──────────────────┘
```

More detail: [docs/HLD.md](docs/HLD.md) · Plan / status: [PROJECT.md](PROJECT.md)

---

## Install

Python ≥3.11.

```bash
uv sync
cp .env.example .env   # API keys — never commit .env
```

Core install includes LiteLLM, PyAI (default speech), LiveKit (Retell), and the local UI server.

Optional extras: `mcp` (MCP server), `dev` (pytest / ruff).

```bash
uv sync --extra mcp    # then: uv run wiretap-mcp
uv sync --extra dev
```

---

## First run

```bash
uv run wiretap init
uv run wiretap simulate --all
uv run wiretap report
```

Connect a live platform agent:

```bash
# Vapi
export VAPI_API_KEY=...
export OPENAI_API_KEY=...   # test-agent LLM + judge
export PYAI_API_KEY=...     # default STT/TTS for voice

uv run wiretap import vapi --assistant-id asst_xxx
uv run wiretap simulate --suite vapi --all

# Retell
export RETELL_API_KEY=...
uv run wiretap import retell --agent-id agent_xxx
uv run wiretap simulate --suite retell --all
```

---

## Commands

| Command | What it does |
| --- | --- |
| `wiretap init` | Create a starter suite in `.wiretap/suites/` |
| `wiretap import …` | Pull platform config and draft scenarios |
| `wiretap suite …` | List / show / path suites |
| `wiretap simulate` | Dial the live agent (`--all` or `--scenario <id>`) |
| `wiretap report` | Summarize local simulation artifacts |
| `wiretap export` | Copy a suite out for git or sharing |
| `wiretap ui run` | Local dashboard at http://127.0.0.1:8787 |

**Simulation** = one scenario run. **Batch** = UI Start of 1..N simulations.

Import fills config; it does not dial. `simulate` dials.

---

## Local UI

```bash
cd ui && npm install && npm run build && cd ..
uv run wiretap ui run
```

First-run onboarding: **Your Agent** → **Test Agent** (LLM + STT/TTS) → **What To Test**. Same `.wiretap/` data as the CLI. Secrets stay in `.env`; the API only reports whether keys are set.

---

## How it works

**Voice calls** (Vapi WebSocket, Retell LiveKit): audio goes over the wire. The transport handles STT/TTS; the test agent decides what to say next in text, then TTS speaks it into the call.

**Test agent ladder** (suite YAML):

1. **Prompt** — persona + goal  
2. **Beats** — pin exact lines on certain turns  
3. **Phases** — multi-step goals via `flow_phases`  

**Scoring:** deterministic rules + LiteLLM judge. Suggestions appear on fail only.

Defaults: LLM **OpenAI** (`gpt-4o-mini`), speech **PyAI**.

---

## Platforms

| Platform | Live dial | Notes |
| --- | --- | --- |
| Vapi | WebSocket PCM (default) | Text Chat if `transport: text` or `room_url: chat` |
| Retell | LiveKit | Set `RETELL_API_KEY` |
| Custom / stub | Text | Local dry-run |
| Bland | Import only | Live phone dial not available yet |
| Phone / SIP | — | Not available yet |

---

## Layout

```text
src/wiretap/
  agent/         # test agent (beats, orchestrator, simulate)
  suite/         # suite YAML + simulation artifacts
  transport/     # Vapi / Retell / text
  providers/     # LLM + STT/TTS
  eval/          # rules + judge
  importers/     # platform import + AgentGraph
  services/      # local UI helpers
  cli/           # Typer commands
  ui/            # FastAPI + static
  mcp/           # optional MCP server
  models.py
  paths.py

.wiretap/        # created in your project cwd
  suites/
  simulations/
  graphs/
  onboard.json
.env             # secrets only
```

---

## Security

- Secrets in **`.env` / environment only** (see `.env.example`)
- Suite YAML stores agent ids and `token_env` **names**, never key values
- Judge suggestions appear **on fail only**

## License

Apache-2.0
