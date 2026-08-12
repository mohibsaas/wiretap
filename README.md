# wiretap

Test your **live** voice agent from the terminal.

Wiretap dials the agent you already deployed (Vapi, Retell, or a text stub) using a **test agent**. It scores the call with rules + an LLM judge, then saves results under `.wiretap/`.

```text
Your live agent  ←── Vapi / Retell / text ──→  Wiretap test agent
                                                      │
                                               Pipecat Flows (what to say)
                                               LiteLLM (talk + judge)
                                               Transport TTS/STT (voice)
```

Design detail: [docs/HLD.md](docs/HLD.md) · Plan / status: [PROJECT.md](PROJECT.md)

---

## Install

Python ≥3.11. Core deps include Pipecat, LiteLLM, and a local UI server.

```bash
uv sync
cp .env.example .env   # put API keys here — never commit .env
```

Optional extras: `retell` (LiveKit), `pyai` (default speech), `mcp`, `dev`.

---

## First run

```bash
uv run wiretap init
uv run wiretap simulate --all --junit junit.xml --json report.json
uv run wiretap report
```

Or connect a platform agent:

```bash
export VAPI_API_KEY=...
export OPENAI_API_KEY=...   # test-agent LLM + judge
export PYAI_API_KEY=...     # default STT/TTS for voice

uv run wiretap import vapi --assistant-id asst_xxx
uv run wiretap simulate --suite vapi --all
```

Retell needs `uv sync --extra retell` and `RETELL_API_KEY`.

---

## Commands

| Command | What it does |
| --- | --- |
| `wiretap init` | Create a starter suite in `.wiretap/suites/` |
| `wiretap import …` | Pull platform config and draft scenarios |
| `wiretap suite …` | List / show / path suites |
| `wiretap simulate` | Dial the live agent for one or all scenarios |
| `wiretap report` | Summarize local simulation artifacts |
| `wiretap export` | Copy a suite out for git/CI |
| `wiretap ui run` | Local dashboard at http://127.0.0.1:8787 |

**Simulation** = one scenario run. **Batch** = UI Start of 1..N simulations.

Import fills config; it does **not** dial. Simulate dials.

---

## Local UI

```bash
cd ui && npm install && npm run build && cd ..
uv run wiretap ui run
```

First-run onboarding: **Your Agent** → **Test Agent** (LLM + STT/TTS) → **What To Test**. Same `.wiretap/` data as the CLI. Secrets stay in `.env`; the API only returns whether keys are set.

---

## How the test agent works

1. **Prompt** — persona + goal in the suite YAML  
2. **Beats** — pin exact lines at certain turns  
3. **Flows** — multi-step phases (`flow_phases`) as Pipecat `NodeConfig` IR  

Utterances and the judge use **LiteLLM**. On a voice call, **TTS/STT run inside the transport** (factory adapters). Defaults: LLM **OpenAI**, speech **PyAI**.

---

## Platforms

| Platform | Live dial | Notes |
| --- | --- | --- |
| Vapi | WebSocket PCM (default) | Text Chat if `transport: text` or `room_url: chat` |
| Retell | LiveKit | `uv sync --extra retell` |
| Custom / stub | Text | CI / dry-run |
| Bland | Import only | Live phone dial deferred |
| Phone / SIP | — | Deferred |

---

## Files on disk

```text
.wiretap/
  suites/        # scenarios (source of truth)
  simulations/   # pass/fail artifacts (local)
  graphs/        # imported AgentGraph IR (data only)
  onboard.json   # non-secret UI prefs
.env             # secrets only
```

---

## Security

- Secrets in **`.env` / environment only** (see `.env.example`)
- Suite YAML stores agent ids and `token_env` **names**, never key values
- Judge suggestions appear **on fail only**

## License

Apache-2.0
