# wiretap — High-Level Design

Wiretap is a CLI that dials **your live voice agent** with a **test agent**, scores the call, and stores results under `.wiretap/`.

## Idea in one picture

```text
   ┌─────────────┐         dial          ┌──────────────────┐
   │   WIRETAP   │ ───────────────────▶  │ Your live agent  │
   │             │   Vapi / Retell /     │                  │
   │  test agent │   text                │  (Retell, Vapi,  │
   │  + judge    │ ◀───────────────────  │   custom, …)     │
   └─────────────┘         reply         └──────────────────┘
```

Three rules:

1. **Import ≠ dial.** Import drafts suites; `simulate` opens the live session.  
2. **AgentGraph is data only.** We never re-run their agent locally.  
3. **Secrets stay in `.env`.** YAML holds ids and `token_env` names.

## Pieces

| Piece | Job |
| --- | --- |
| `TestAgentOrchestrator` | Turn-based policy for what the test agent says |
| `FlowNode` / phases | Prompt → beats → `flow_phases` |
| LiteLLM | Test-agent lines + judge |
| Transport | Session to the live agent; voice TTS/STT here |
| Rules + judge | Pass/fail + fail-only tips |

The CLI loop is turn-based against a live transport. Voice audio goes through transport `configure_speech` / factory adapters — not a separate media pipeline framework.

## One simulation

```text
suite.yaml
   │
   ▼
simulate_scenario
   ├── build_transport(agent)
   ├── configure_speech(stt/tts)     # voice transports only
   ├── build_orchestrator(...)       # phases + LiteLLM
   │
   ├── loop (max_turns)
   │     receive agent text
   │     next test-agent utterance (beats / node steps)
   │     send text (TTS on voice transports)
   │
   ├── caller-contract check (--strict → inconclusive)
   ├── rules + LiteLLM judge
   └── SimulationArtifact → .wiretap/simulations/
```

## Speech defaults

| Slot | Default | Notes |
| --- | --- | --- |
| LLM | OpenAI (via LiteLLM) | Simulator + judge model slots |
| STT / TTS | PyAI | Speech-only; not an LLM |

Factory adapters also cover OpenAI, Deepgram, Cartesia, ElevenLabs, and similar HTTP providers.

## Surfaces

| Surface | Role |
| --- | --- |
| CLI | `init \| import \| suite \| simulate \| report \| export \| ui` |
| Local UI | Onboarding + agents / suites / evaluations |
| MCP | Optional `wiretap-mcp` |

## Data layout

```text
.wiretap/
  suites/           # scenario definitions
  simulations/      # artifacts (local; not “results in git”)
  graphs/           # imported AgentGraph IR
  onboard.json      # non-secret prefs
.env                # secrets only
```

## Not in this repo (yet)

- Phone / SIP / Bland live dial  
- Owning telephony  
- Executing AgentGraph locally  
- Cloud SaaS product  

## Diagram

```mermaid
flowchart LR
  subgraph W["WIRETAP"]
    A[test agent + judge]
  end
  L[Your live agent]
  W -->|"dial (Vapi / Retell / text)"| L
  L -->|reply| W
```
