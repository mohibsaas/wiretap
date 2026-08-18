# Wiretap Documentation

Wiretap is a CLI-first, local-first voice agent test simulator. It dials your **live deployed** voice agent, simulates an LLM-driven test caller, records the conversation, and scores it with deterministic rules plus an LLM judge.

## Documentation index

| Document | Description |
|----------|-------------|
| **[First-time setup](./setup.md)** | **Install, API keys, `wiretap init`, and first simulation** |
| [Architecture](./architecture.md) | System design, components, data flow, interfaces, and platform support |
| [Robustness](./robustness.md) | Error handling, retries, failure modes, concurrency limits, and isolation guarantees |
| [Production readiness](./production-readiness.md) | Deployment patterns, CI integration, security posture, observability, and hardening checklist |
| [High-level design (HLD)](./HLD.md) | One-page overview — start here for a quick mental model |

## Quick reference

```text
wiretap init → wiretap import → wiretap simulate → wiretap report
                     ↓
              ~/.wiretap/suites/*.yaml
                     ↓
         live dial (WebSocket / LiveKit / PSTN)
                     ↓
         ~/.wiretap/simulations/*.jsonl + evaluations/
```

## Surfaces

| Surface | Entry point | Use case |
|---------|-------------|----------|
| CLI | `wiretap` | Terminal workflows, CI pipelines |
| Local UI | `wiretap ui run` | Onboarding, batch runs, prompt fixes |
| MCP | `wiretap-mcp` | Agent-driven testing from Cursor / Claude |

## Data layout

All runtime data lives under `~/.wiretap/` (or `$WIRETAP_HOME`):

```text
~/.wiretap/
  .env              # Secrets only (chmod 600)
  onboard.json      # Non-secret onboarding preferences
  suites/           # Test suite definitions (YAML)
  graphs/           # Imported AgentGraph IR (data only)
  simulations/      # Per-call artifacts (JSONL, append-only by day)
  evaluations/      # Batch summaries + *.progress.json sidecars
```

## Core design rules

1. **Import ≠ dial.** Import drafts suites; `simulate` opens live sessions to your deployed agent.
2. **AgentGraph is IR only.** Wiretap never executes your agent graph locally.
3. **Secrets stay in `.env`.** Suite YAML holds IDs and `token_env` names — never key values.
4. **One scenario = one isolated session.** No shared session state across parallel runs.
5. **Voice-first.** Text transport exists as a CI/fallback stub.

## Related files

- [README.md](../README.md) — User-facing quick start and feature overview
- [PROJECT.md](../PROJECT.md) — Product thesis and locked architectural decisions
- [SECURITY.md](../SECURITY.md) — Vulnerability reporting policy
- [.env.example](../.env.example) — Secret key reference
