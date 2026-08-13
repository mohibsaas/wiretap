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

**Use `wiretap` on your PATH** (recommended while developing):

```bash
uv tool install --editable .
wiretap --help
```

Or activate the project venv: `source .venv/bin/activate`, then `wiretap …`.  
`uv run wiretap …` also works without activating — same binary, just via uv.

Optional extras: `mcp` (MCP server), `dev` (pytest / ruff).

```bash
uv sync --extra mcp    # then: uv run wiretap-mcp   (or wiretap-mcp after tool install)
uv sync --extra dev
```

---

## Usage

### Known platforms (Vapi / Retell)

Import pulls the live agent config, then **generates category-tagged tests via LLM**
(defaults: `emotional`, `compliance`, `task` — 3 tests each). Uses your configured
simulator model (LiteLLM). Regenerate anytime with `wiretap suite generate`.

```bash
# Vapi
export VAPI_API_KEY=...
export OPENAI_API_KEY=...
export PYAI_API_KEY=...

uv run wiretap import vapi --assistant-id asst_xxx
# optional: pick categories
# uv run wiretap import vapi --assistant-id asst_xxx \
#   --categories emotional,adversarial,task --tests-per-category 5
# uv run wiretap import vapi --assistant-id asst_xxx --smoke-only   # no category tests

uv run wiretap simulate --suite vapi --all
uv run wiretap report

# Retell
export RETELL_API_KEY=...
uv run wiretap import retell --agent-id agent_xxx
uv run wiretap simulate --suite retell --all
```

**Generate or refresh tests later** (keeps the same agent target):

```bash
uv run wiretap suite categories
uv run wiretap suite generate --suite vapi \
  --categories emotional,linguistic,compliance --tests-per-category 5 \
  --purpose "cancellation and refunds"
```

Same flow in the UI: connect agent → configure test agent → pick categories → generate.

### Any / custom agent

Hand-write a suite under `.wiretap/suites/<name>.yaml` (or `wiretap export` a suite and edit it). Point `agent:` at how wiretap should reach them:

```yaml
agent:
  platform: vapi          # vapi | retell | null
  agent_id: asst_xxx      # platform id when using vapi/retell
  transport: webrtc       # or text for dry-run
  token_env: VAPI_API_KEY # env var *name* — never the key itself

# or local text stub (no platform):
# agent:
#   platform: null
#   transport: text
```

Then:

```bash
uv run wiretap simulate --suite <name> --all
uv run wiretap report
```

`platform: null` + `transport: text` is a local echo stub for dry-runs. Live custom SIP/phone is not available yet — use a supported platform endpoint, or text for offline checks.

### Day-to-day loop

```text
import or edit suite  →  simulate (--all or --scenario)  →  report
```

---

## Commands

| Command | What it does |
| --- | --- |
| `wiretap import …` | Pull platform agent + generate category tests |
| `wiretap suite …` | list / show / path / categories / generate |
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

**Test categories** (many tests per category; catch-all = `other`):

| Id | Focus |
| --- | --- |
| `emotional` | Frustrated, anxious, angry, sensitive |
| `linguistic` | Ambiguity, repair, interruptions, language |
| `adversarial` | Jailbreaks, social engineering, PII fishing |
| `operational` | Hours, handoff, errors, callbacks |
| `factual` | No invented prices/IDs/features |
| `compliance` | Disclosures, verification, privacy |
| `task` | Happy-path / core job completion |
| `other` | Misc that does not fit above |

Skipped/pending/running in a results grid are **run states**, not generation categories.

---

## Platforms

| Platform | Live dial | Notes |
| --- | --- | --- |
| Vapi | WebSocket PCM (default) | Text Chat if `transport: text` or `room_url: chat` |
| Retell | LiveKit | Set `RETELL_API_KEY` (needs Testing.Write) |
| ElevenLabs Agents | ConvAI WebSocket | Set `ELEVENLABS_API_KEY` |
| LiveKit Agents | LiveKit room | `agent_id` = room name, `room_url` = `wss://…`; `LIVEKIT_API_KEY` + `LIVEKIT_API_SECRET` (or `LIVEKIT_TOKEN`) |
| Synthflow | WS media | `SYNTHFLOW_API_KEY` + `SYNTHFLOW_FROM_NUMBER` / `SYNTHFLOW_TO_NUMBER` |
| Custom / stub | Text | Local dry-run (`platform: null`) |
| Bland / Bolna | Import only | Live phone dial not available yet |
| Phone / SIP | — | Not available yet |

---

## Layout

```text
src/wiretap/
  agent/         # test agent (beats, orchestrator, simulate)
  suite/         # suite YAML + simulation artifacts
  transport/     # Vapi / Retell / ElevenLabs / LiveKit / Synthflow / text
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
