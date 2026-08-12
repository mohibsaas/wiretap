# wiretap — Final Plan

OSS, **CLI-first** voice-agent test simulator. Local-first, CI-capable, with a local dashboard.

**CLI / package:** `wiretap` (Python + **Typer** ≈ Commander.js)

---

## 1. Product thesis

Developers test **their live voice agents** from the terminal and get a report.

- **Simulator** = fake caller (persona + goal; optional beats / Pipecat Flows)
- **Live agent** = their deployed agent (Retell, Vapi, Bland, LiveKit, custom, …)
- **Judge** = LLM-as-judge + rule checks; **suggestions only on fail**
- **Import** = optional: fetch platform config + draft suites
- **Export** = optional: copy local suites out for git/CI/teammates
- We **do not** rebuild or execute their agent graph locally

Starting point for users:

```text
wiretap init → edit local suite → wiretap simulate → wiretap report
(optional) import / export / CI
```

---

## 2. Locked decisions

| Area | Decision |
| --- | --- |
| Name | **wiretap** |
| Language | Python ≥3.11 |
| Packaging | **uv** — `uvx wiretap` / `uv tool install wiretap` |
| CLI framework | **Typer** (Commander-style: verbs + nested subcommands) |
| LLM | **LiteLLM** (simulator + judge; separate model slots) |
| Simulator media | **Pipecat ≥1.5.0** |
| Caller structure | Ladder: **prompt → beats → `pipecat.flows`** (Flows in-core, no separate package) |
| Multi-agent (advanced) | Pipecat **Worker Bus** (handoff / fan-out / local or distributed) |
| LangGraph | **Not on the Pipecat path** — Flows + Worker Bus cover it |
| AgentGraph | **IR only** for imports — **no execution engine** |
| STT/TTS | Adapter ABCs; **pyai** soft-default; optional `wiretap[pyai]` |
| Transports | **Voice-first:** WebSocket + LiveKit; `text` is CI/fallback. Phone/SIP deferred |
| Platforms | Retell / Vapi / Bland presets; generic target always works |
| Suite storage | **Default:** `.wiretap/suites/` (local) |
| Export | `wiretap export` → opt-in copy for git/CI |
| Simulations / reports | `.wiretap/simulations/` only — never the suite source of “results in git” |
| Secrets | Env vars only — YAML holds ids + `token_env` names, never keys |
| Eval | Judge + rules + metrics + regression; suggestions **on fail only** |
| Isolation | One scenario = one caller + one session + one artifact |
| Concurrency | `asyncio` + semaphore; no shared session state |
| MCP | Optional `wiretap-mcp` wraps core |
| License | Apache-2.0 |
| UI | Local dashboard via `wiretap ui run` (FastAPI/uvicorn are core deps). Cloud dashboard out of scope |
| Cloud | Out of scope; SimulationArtifact schema stays ingest-friendly |

---

## 3. CLI (Commander-style)

```text
wiretap
├── init [--name default]          # → .wiretap/suites/<name>.yaml
├── import
│   ├── retell  --agent-id
│   ├── vapi    --assistant-id
│   └── bland   --pathway-id
├── suite list | show | path
├── simulate [--suite] [--all] [--concurrency N]
├── report  [--suite]
├── export  [--suite] --out <dir>
├── ui run  [--host] [--port] [--open/--no-open]
└── --help / --version
```

**Glossary:** a **simulation** is one scenario execution (artifact). A **batch** is one UI “Start” that may execute 1..N simulations. `wiretap simulate` executes simulations from the CLI; `wiretap ui run` starts the dashboard server.

**Write suite files:** `init`, `import`, `export` only (explicit).  
**`simulate` / `report`:** do not rewrite suite YAML; `simulate` appends under `.wiretap/simulations/`.

Does **not** modify the wiretap package itself (same as `uv init` writing *your* project, not uv’s source).

---

## 4. How users connect a platform agent

```text
1. export RETELL_API_KEY=…   (or VAPI_ / BLAND_)
2. wiretap import retell --agent-id agent_xxx
   → drafts .wiretap/suites/… with platform + id + sample scenarios
   OR hand-edit agent: { platform, agent_id, transport }
3. wiretap simulate --all
   → transport adapter starts WebRTC/session to THEIR live agent
4. wiretap report
```

**Import ≠ transport.** Import fills config/tests; simulate dials the live agent.

---

## 5. Caller ladder (versatile, progressive)

| Level | Mechanism | Who |
| --- | --- | --- |
| **1. Prompt** | Persona + goal + rubric in suite YAML | Default |
| **2. Beats** | Pin `say` / `must_include` at `at_turn` / `after_turns` | CI / stricter suites |
| **3. Flows** | `pipecat.flows` node graph for the caller | Power users |

Same runner: `CallerPolicy` seam (`observe_agent` / `next_utterance`).  
Beats = thin v1 feature. Flows when beats aren’t enough. Worker Bus only for specialist/parallel callers later.

---

## 6. Suite & storage layout

```text
.wiretap/
  suites/           # default definitions (local)
    default.yaml
  graphs/           # AgentGraph IR from import (data only)
  simulations/      # simulation artifacts (local)
```

- Solo: stay under `.wiretap/` — test agent → get report  
- Share/CI: `wiretap export --out ./suites/`  
- Also: `wiretap simulate --suite ./path/to.yaml` for project-tracked suites  

Suites are **config**, not “test simulations in git.” Simulation artifacts under `.wiretap/simulations/` never need to be committed.

---

## 7. Architecture (HLD)

```text
                    ┌─────────────────────────┐
                    │  User already has a     │
                    │  live voice agent       │
                    └───────────┬─────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────┐
│  Typer CLI: init | import | simulate | report | export            │
└────────────────────────────┬─────────────────────────────────┘
                             ▼
              .wiretap/suites/*.yaml  (local default)
                             ▼
┌──────────────┬─────────────────────────┬─────────────────────┐
│ Importers    │ Runner (per scenario    │ Eval                │
│ → draft      │  isolated)              │ Judge + rules       │
│   suite +    │ CallerPolicy:           │ Suggestions on fail │
│   AgentGraph │  prompt | beats | flows │ Metrics + regression│
│   IR (data)  │ Pipecat media + STT/TTS │                     │
└──────┬───────┴─────────────┬───────────┴──────────┬──────────┘
       │                     ▼                      │
       │              Transport adapters            │
       │              text | webrtc | sip | pstn    │
       │                     ▼                      ▼
       │              THEIR live agent         .wiretap/simulations/
       └──────────────────────────────────────────────────────
```

---

## 8. Evaluation

- Pass/fail + reason (judge)  
- Deterministic rules (`includes` / `excludes` / `patterns`)  
- Latency / turns when available  
- Regression vs baseline → CI exit code  
- **Suggestions only when failed** (shown in `simulate` + `report` by default; not a gate)  

Trust the fake caller via: strict mode, beats for critical lines, optional caller meta-check → inconclusive if caller went off-rails.

---

## 9. Status (implemented)

| Area | Status |
| --- | --- |
| CLI `init \| import \| suite \| simulate \| report \| export \| ui` | Done |
| Prompt + beats + `flow_phases` caller | Done (via Pipecat Flows orchestrator) |
| Judge + rules + fail-only suggestions + regression | Done |
| AgentGraph IR + Retell/Vapi/Bland importers | Done |
| STT/TTS factory (pyai/openai + Deepgram/Cartesia/ElevenLabs/…) | Done |
| Meta-check / `--strict` → inconclusive | Done |
| JUnit/JSON + GitHub Actions | Done |
| Vapi WS voice + Retell LiveKit + text Chat fallback | Done |
| Phone / SIP / Bland live dial | Deferred |
| MCP (`wiretap-mcp`) | Done |
| Pipecat core dep + Flows orchestrator + STT→LLM→TTS pipeline | Done |

### Still later
- Phone / SIP / PSTN (inbound + outbound)  
- Worker Bus multi-specialist callers  
- Audio stress / ASR intended-vs-heard  
- Azure/Google/AWS speech (need cloud IAM beyond a single API key)  
- Separate closed cloud (not this repo)  

### Non-goals
- Dashboard in OSS  
- Hard dep on any one LLM/STT/TTS (including pyai)  
- Owning telephony infra  
- AgentGraph execution / local live-agent emulation  
- LangGraph as core orchestration  

---

## 10. One-line summary

**wiretap is a Typer CLI that keeps suites local under `.wiretap/`, calls your live voice agent with a prompt/beats/Flows caller, scores with a judge (suggestions on fail), and exports suites only when you want them in git/CI.**

## 11. Live platform transports (implemented)

| Platform | Mechanism |
| --- | --- |
| **Vapi** | **Default: WebSocket PCM voice** (TTS/STT). Text Chat only if `transport: text` or `room_url: chat` |
| **Retell** | LiveKit web-call (`uv sync --extra retell`); TTS in, transcript out |
| **Bland** | Import/IR only for now — live phone dial deferred |
| **Stub** | No platform — local text echo for CI |
| **Phone / SIP** | Deferred |
