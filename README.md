# wiretap

CLI-first **voice agent test simulator**. Dial your **live** agent with a Pipecat-orchestrated **test agent**, score the call (LiteLLM judge + rules), and keep everything local under `.wiretap/`.

Voice is the default. Text Chat is an opt-in for CI / cheap dry-runs.

**Design:** [docs/HLD.md](docs/HLD.md) · **Plan / status:** [PROJECT.md](PROJECT.md)

```text
Your live agent  ←── Vapi WS / Retell LiveKit / text ──→  Wiretap test agent
                                                              │
                                                      Pipecat Flows IR
                                                      LiteLLM + STT/TTS
                                                      Judge (fail-only tips)
```

---

## Quick start

```bash
uv sync
cp .env.example .env   # fill keys — never commit .env

uv run wiretap init
uv run wiretap simulate --all --junit junit.xml --json report.json
uv run wiretap report
```

Python ≥3.11. Core deps include **Pipecat**, **LiteLLM**, FastAPI/uvicorn (local UI), and websockets (Vapi voice).

---

## CLI

```text
wiretap
├── init                 # starter suite → .wiretap/suites/
├── import retell|vapi|bland
├── suite list|show|path
├── simulate             # one or many scenarios
├── report
├── export               # copy suite out for git/CI
└── ui run               # local dashboard
```

Glossary: a **simulation** is one scenario run; a **batch** is a UI Start of 1..N simulations.

---

## Local dashboard

```bash
cd ui && npm install && npm run build && cd ..   # once / after UI changes
uv run wiretap ui run                           # → http://127.0.0.1:8787
```

First-run **onboarding**:

1. **Your Agent** — Retell / Vapi / custom (platform key + agent id)
2. **Test Agent** — LLM (LiteLLM providers) + STT/TTS (PyAI first for speech) + keys
3. **What To Test** — purpose, categories, generate suite

Same `.wiretap/` data as the CLI. Secrets go to `.env` only (API returns booleans, never key values).

---

## Live platforms

| Platform | Live dial | Notes |
| --- | --- | --- |
| **Vapi** | WebSocket PCM voice (default) | Text Chat if `transport: text` or `room_url: chat` |
| **Retell** | LiveKit web-call | `uv sync --extra retell` |
| **Custom** | Text stub | CI / dry-run |
| **Bland** | Import only | Live phone dial deferred |
| **Phone / SIP** | Deferred | — |

```bash
# Vapi
export VAPI_API_KEY=...
# Test agent speech + LLM (examples)
export OPENAI_API_KEY=...
export PYAI_API_KEY=...          # default STT/TTS
uv run wiretap import vapi --assistant-id asst_xxx
uv run wiretap simulate --suite vapi --all

# Retell
export RETELL_API_KEY=...
uv sync --extra retell
uv run wiretap import retell --agent-id agent_xxx
uv run wiretap simulate --suite retell --all
```

---

## Test agent stack

| Piece | Role |
| --- | --- |
| **Pipecat Flows** | Orchestrator IR (`NodeConfig` nodes; prompt → beats → `flow_phases`) |
| **LiteLLM** | Test-agent utterances + judge |
| **STT** | PyAI, OpenAI, Deepgram, AssemblyAI, Gladia, Groq |
| **TTS** | PyAI, OpenAI, Deepgram, Cartesia, ElevenLabs, LMNT, Rime, PlayHT |

Defaults: **LLM OpenAI**, **STT/TTS PyAI** (PyAI is speech-only — not an LLM). Configure in onboarding or suite `speech:` / `models:`.

---

## Layout

```text
wiretap/
├── src/wiretap/     # Python package (CLI, services, transports, UI static)
├── ui/              # Vite React source → builds into src/wiretap/ui/static/
├── docs/HLD.md
├── tests/
└── pyproject.toml

.wiretap/            # created in your project cwd
├── suites/
├── simulations/
├── graphs/
└── onboard.json
.env                 # secrets only
```

---

## MCP (optional)

```bash
uv sync --extra mcp
uv run wiretap-mcp
```

---

## Security

- Secrets in **environment / `.env` only** (see `.env.example`)
- Suite YAML holds agent ids + `token_env` **names**, never keys
- Do not commit `.env`
- Suggestions from the judge appear **on fail only**

---

## License

Apache-2.0
