# wiretap

Test your **live** voice agent from the terminal.

Wiretap dials the agent you already run (Vapi, Retell, or a text stub) with its own **test agent**, scores the call with rules + an LLM judge, and stores results under **`~/.wiretap/`** (override with `WIRETAP_HOME`).

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
```

**First run (recommended):** interactive setup writes keys to `.env` — same flow as the UI.

```bash
uv tool install --editable .   # or: source .venv/bin/activate
wiretap init                   # test agent → optional live agent → suite
wiretap status                 # what's configured (no secret values)
```

Or hand-edit secrets:

```bash
# Default secrets path (created by wiretap init):
#   ~/.wiretap/.env
# Optional: also load a project ./ .env for missing keys
# Override data dir:
#   export WIRETAP_HOME=/path/to/my-wiretap-data
```

Core install includes LiteLLM, PyAI (default speech), LiveKit (Retell), and the local UI server.

**Use `wiretap` on your PATH** (recommended while developing):

```bash
uv tool install --editable .
wiretap --help
```

Or activate the project venv: `source .venv/bin/activate`, then `wiretap …`.  
`uv run wiretap …` also works without activating — same binary, just via uv.

Optional extras: `pstn` (real phone calls), `mcp` (MCP server), `dev` (pytest / ruff).

```bash
uv sync --extra pstn   # Twilio + SIP softphone, needed for `--transport phone`
uv sync --extra mcp    # then: uv run wiretap-mcp   (or wiretap-mcp after tool install)
uv sync --extra dev
```

---

## Usage

### Quick start (CLI onboarding)

```bash
wiretap init
# 1) pick LLM + STT/TTS and paste keys (saved to .env only)
# 2) optionally connect Retell/Vapi/…
# 3) optionally generate a category suite
# 4) optionally set up Twilio for real phone calls

wiretap simulate -s <suite> --all
wiretap report
```

Import still prompts for a missing platform key when run in a TTY:

```bash
wiretap import retell --agent-id agent_xxx
# or pass once: --api-key "$RETELL_API_KEY"
```

### Known platforms (Vapi / Retell)

Import pulls the live agent config — prompt, flow, variables and **tools** — then
**generates category-tagged tests via LLM** (defaults: `emotional`, `compliance`,
`task` — 3 tests each). Uses your configured simulator model (LiteLLM).
Regenerate anytime with `wiretap suite generate`.

Only tool names, descriptions and argument names are captured. Webhook URLs and
tool auth headers are dropped at import, so they never reach `~/.wiretap/graphs/`
or the generation prompt.

Generation is **grounded in the imported agent**: its role, goals, stated constraints,
tools and flow nodes are summarized into an agent brief and sent with the prompt, so
scenarios probe what your agent actually does. The brief is sanitized first — API keys,
tokens, emails, phone numbers and long account ids are redacted, and the prompt excerpt
is truncated — but it does leave your machine in the LLM payload. Use `--smoke-only` to
skip LLM generation entirely.

```bash
# After wiretap init (or with keys already in .env)
uv run wiretap import vapi --assistant-id asst_xxx
# optional: pick categories
# uv run wiretap import vapi --assistant-id asst_xxx \
#   --categories emotional,adversarial,task --tests-per-category 5
# uv run wiretap import vapi --assistant-id asst_xxx --smoke-only   # no category tests

uv run wiretap simulate --suite vapi --all
uv run wiretap report

# Retell
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

Refills read the agent brief back from `~/.wiretap/graphs/<suite>.graph.json`, so an
imported suite stays grounded without another API call. Without a graph (a
`--purpose`-only suite) generation falls back to purpose plus category guidance.

Same flow in the UI: connect agent → configure test agent → pick categories → generate.

### Testing over a real phone call

Web or phone is a **per-run choice**, so the same suite works both ways and the
YAML never changes. `simulate` asks in a terminal, and flags skip the prompts:

```bash
uv sync --extra pstn
uv run wiretap simulate --suite retell --all --transport phone
# non-interactive: name both ends
# uv run wiretap simulate -s retell --all --transport phone \
#   --phone +14155550123 --from-number +14155550199
```

`--phone` is the agent's number; `--from-number` is the Twilio number you dial
from. Left out, wiretap reads the numbers bound to your agent (Retell and Vapi)
and offers them, then remembers the pick for that agent.

Wiring is REST-only — no webhooks or tunnels. A local softphone registers to a
SIP domain wiretap provisions on **your own** Twilio account, and Twilio bridges
that leg to the agent's number. Set `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`
(`wiretap init` step 4 prompts for both); `TWILIO_SIP_PASSWORD` is generated and
rotated for you. Calls cost real Twilio money and run one at a time, since a
single softphone answers them.

Tool calls are still captured: the platform's own call id is recovered from
Retell or Vapi after hangup. Other platforms report tools as unobservable.

### Any / custom agent

Hand-write a suite under `~/.wiretap/suites/<name>.yaml` (or `wiretap export` a suite and edit it). Point `agent:` at how wiretap should reach them:

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

`platform: null` + `transport: text` is a local echo stub for dry-runs. To reach a
custom agent for real, give it a phone number and run `simulate --transport phone`
— that path only needs a dialable number, not a supported platform API.

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
| `wiretap simulate` | Dial the live agent (`--all` or `--scenario <id>`, `--transport web\|phone`) |
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

First-run onboarding: **Your Agent** → **Test Agent** (LLM + STT/TTS) → **What To Test**. Same `~/.wiretap/` data as the CLI. Secrets stay in `~/.wiretap/.env`; the API only reports whether keys are set.

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
| Bland / Bolna | Import only | No platform dial; reachable via `--transport phone` |
| Phone / PSTN | Twilio SIP bridge | Any platform, `uv sync --extra pstn` + `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` |

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

.wiretap/        # default: ~/.wiretap  (or $WIRETAP_HOME)
  suites/
  simulations/
  graphs/
  onboard.json
  .env           # secrets (also created by wiretap init)
```

---

## Security

- Secrets in **`.env` / environment only** (see `.env.example`)
- Suite YAML stores agent ids and `token_env` **names**, never key values
- Judge suggestions appear **on fail only**

## License

Apache-2.0
