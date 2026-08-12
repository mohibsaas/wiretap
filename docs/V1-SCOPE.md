# Wiretap V1 — Scope and Decisions

> **Build from `BUILD-SPEC.md`.** This doc records the *decisions*; BUILD-SPEC turns them into schema + build instructions. Companion authoring docs: `GENERATION-PROMPTS.md`, `TECHNIQUE-CATALOGUE.md`.

**Date:** 2026-08-12 · **Status:** decided (this doc records product decisions made 2026-08-12; it overrides recommendations in `LANGWATCH-RESEARCH.md` §7.4 where they conflict)
**Reading order:** this doc → `REVIEW-FINDINGS.md` (defects to fix) → `ARCHITECTURE.md` → `SUITE-LIFECYCLE.md` → `LANGWATCH-RESEARCH.md` (patterns).
**UI note:** final UI ships after designer handoff; V1 builds the core with functional screens only.

---

## 1. Decisions (all made 2026-08-12)

| # | Question (source) | Decision |
|---|---|---|
| D1 | S1 — generation now or v1.1? | **In V1** — full test generation, driven by a basic prompt template per category + agent config |
| D2 | Prompt-aware generation (was v2) | **In V1** — generation may read the stored system prompt where the vendor exposes it |
| D3 | Retell in or out? (W0 cut #1 said out) | **In.** Accept the 8–12 h WebRTC cost. ⚠️ Retell's ToS prohibition on this kind of testing is a *business* risk that needs an explicit owner and a re-read of their current ToS |
| D4 | Onboarding shape | **Key-entry-first, real providers only.** No zero-key loopback-first onboarding flow (the loopback transport is still built — see §4 — but as a dev/demo tool, not the onboarding path) |
| D5 | Pricing / cost display | **Placeholder rates for now.** Real pricing shared later; the estimate formula and `pricing.yaml` structure ship with placeholder values. All amounts shown pre-run are estimates (F11: no real-time spend signal exists from any vendor) |
| D6 | BYO-Twilio + SIP/PSTN | **Never** (dropped, not deferred) |
| D7 | Deepgram adapter | **Not needed** (dropped) |
| D8 | MCP server surface (W0 cut #14 said out) | **In V1** — the 6-tool surface from PRD §13 |
| D9 | Leaderboard (was v1.3) | **In V1.** ⚠️ Depends on the still-unwritten CI story: composite score formula, GitHub Action, signed `result.json` verification. That story must be written before leaderboard build starts |
| D10 | Judge panel (v1.2 item) | **Deferred to v1.2.** Single blinded judge in V1 with published calibration; schema already accommodates the panel (`judge_vote` lands in v1.2, zero rework) |

## 2. V1 scope — what gets built

### Onboarding (key-first)
1. Enter provider API keys — **Vapi, PyAI, Retell** (validated live; `wiretap doctor` re-checks)
2. Select provider
3. Import agents (`AgentImporter.list_agents()`, idempotent upsert on `UNIQUE(vendor, external_id)`)
4. Select agent; config snapshot taken (`agent_config_version`); prompt-access choice (`none | transient | stored`) with consequences stated inline

### Test flow
1. Select test categories (pre-defined rows in `test_category`; user packs can add rows)
2. **Generate test cases** — V1 pipeline:
   - Input: category prompt template + parsed agent config + (where `prompt_access='stored'`) the system prompt
   - One LLM generation stage; user picks count per category in the UI (replaces W2's deterministic plan stage)
   - **Validation kept** (non-negotiable): schema + ≥1 blocking assertion, fingerprint dedup, **stop-word linter** against `agent_config_version.end_call_phrases`, capability subset
   - **C2 kept**: safety-category templates embed cited techniques only — the generator instantiates, never invents, attack content; generated suites are `publishable=0`
   - `generation_job` + HTTP 202 + SSE progress
   - Output is an immutable `suite_version`; regeneration creates a new version, carries manual tests forward (E2)
   - Retell path: `prompt_access='none'` → config-only generation; UI states "generated from config only — weaker coverage"
3. Run tests — pre-flight gates (keys, attestation, smoke call, worst-case spend confirm, concurrency clamp), audio prep/cache, fan-out, live grid, scoring after teardown, stored `run_score` with `scorer_version`
4. Pre-run cost estimate shown (placeholder `pricing.yaml` rates × expected durations × test count, labelled *estimate*)

### Results / UI (core, pre-design)
- Test table (origin badge, citation link, enabled toggle, last result) and suite list
- Simulations & reports: live grid → results → call detail (combined dual-tinted waveform, assertion flags, STT diff) → `report.md` / `report.html`
- Report card (grade, n/N, tier breakdown, 3 worst failures, latency p95 + concurrency label, cost lines, run hash, framing line)
- Badge: shareable score badge — part of the leaderboard/CI story (D9), specced together with it
- MCP surface (6 tools) alongside CLI + HTTP/SSE

### Infrastructure (from W0's "missing" list — all V1)
Migrations (`PRAGMA user_version` + runner + `db reset`) · `run --resume` · `reap` · `prune` · `verify` · `rebuild --dry-run` · error taxonomy (`error_kind` enum) · bounded writer queue (drop `wire_event` first) · byte counters + silent-drop invariant · `payload_blob` content addressing (F12) · loopback/fixture transport (hour-1, CI target for gates 2,3,4,6,8,9,10,11,12).

### Schema
Runtime 8–10 tables (post-cut set incl. `run_score`) + authoring: `agent`, `agent_config_version`, `agent_goal` (needed again now that prompt-aware generation is in), `test_category`, `test_case`, `test_case_goal`, `generation_job`, `suite`, `suite_version`, `suite_test`. Standard corpus seeded into `test_case` rows from the YAML pack (answers S2 = rows).

## 3. Consequences of D2 (prompt-aware in V1) — must-do list

Storing customer system prompts pulls these forward from v2:
- `prompt_access='stored'` flow with an **attestation row** before any prompt is persisted
- Restated trust claim: *"your prompt is never transmitted to a third party except the judge/generator model you selected, and never persisted unless you choose `stored`"*
- **F12 denylist is now critical-path**: Vapi ships the full system prompt on every `conversation-update` frame — the redaction denylist must cover the customer prompt, `websocketCallUrl`, `listenUrl`/`controlUrl`, presigned URLs, `resume_token`, keys/tokens
- `prompt_sha256` recorded always (even at `none`) so prompt drift invalidates a suite

## 4. Explicitly out / deferred

| Item | Status |
|---|---|
| SIP/PSTN, BYO-Twilio | **Never** (D6) |
| Deepgram adapter | Dropped (D7) |
| Judge panel (`judge_vote`, majority vote, 3 model families) | v1.2 (D10) |
| Audio-native judge/scorers | v1.2 |
| `dispute` + golden set + annotation splits | v1.2 |
| `judge_cache` (low hit rate vs live agents) | v1.2 |
| Production-traffic monitoring / `mode='observed'` | v1.3 (as source adapter + `run_source`, per F3) |
| Staging → human review → finalize gate on generation | v1.1 candidate (~2–3 h; revisit once generation is in users' hands) |
| Full goal-extraction quality work (S3/S4) | Open — V1 ships basic extraction; quality bar TBD |

## 5. Still blocking before core code (unchanged from LANGWATCH-RESEARCH §7.4)

1. **Two probes (~30 min, ~$0.25) before any `RunEngine` code**: (a) does `vapi.websocket` queue silently past the concurrency limit? — decides whether the live grid and every latency number are honest; (b) does a 3-beat reactive spine complete against a live agent? — F6 lost-wakeup check.
2. **Composite score formula + CI story** (now also blocks leaderboard + badge, D9). Write it down first.
3. **Retell ToS sign-off** (D3 owner).
4. Apply W0's defect fixes as part of the build, not after: F1 (verify + `caller_audio_set_sha256`), F5 (`run_score`), F6/F7/F13 (call loop), F10 (`evidence_source`), F11 (unsettled cost), F12 (payload dedup), F14 (latency bias fields).
