# Wiretap — Code vs BUILD-SPEC gap map

**Date:** 2026-08-12 · Compares the running codebase at `~/wiretap` against `BUILD-SPEC.md`.

## The headline: two design lines, and the code follows the lighter one

`~/wiretap` is a **real, working product** (~5,200 LOC Python + React UI, tests, MCP). But it was built to `~/wiretap/PROJECT.md` + `docs/HLD.md`, which is a **deliberately lighter design** than the `wiretap-docs` line (ARCHITECTURE/SUITE-LIFECYCLE/REVIEW-FINDINGS → BUILD-SPEC). They are not the same product at two completion levels — they diverge on foundations:

| Dimension | Code (`PROJECT.md`) | BUILD-SPEC (`wiretap-docs`) |
|---|---|---|
| Storage | YAML suites + JSONL artifacts under `.wiretap/` | SQLite (20 tables) + files under `./data` |
| Test agent | Turn-based **text** loop (`send_text`/`receive`) | **PCM audio** reactive spine (RMS, barge-in, F6/F7/F13) |
| Generation | **Template** catalog (hardcoded, ~10/category) | **LLM**, prompt-aware, validated, cited (C2) |
| Suites | Mutable YAML | Immutable `suite_version`, content-hashed |
| Determinism | none | SHA-256 caller-audio cache + `verify` |
| Safety | none | attestation, pre-flight gates, ToS registry |
| Cost | none | pricing.yaml, budget governor, cost columns |
| Judge | LiteLLM `judge_call` | blinded + published κ calibration |
| CI/leaderboard | **explicit non-goal** | in scope (signed result.json + Action) |
| License | Apache-2.0 | (docs said MIT) |

**Decision the user owns:** grow the code toward BUILD-SPEC, or trim BUILD-SPEC toward the code's philosophy. §4 gives a recommendation.

---

## 1. What EXISTS (have)

| BUILD-SPEC area | In code | Where |
|---|---|---|
| Key-first onboarding + provider key mgmt | ✅ | `services/onboard.py`, `services/secrets.py`, `providers/catalog.py`, `ui/pages/OnboardPage.tsx` |
| Provider key validation / status | ✅ | `onboard_status()` |
| The 7 categories (emotional…task) | ✅ | `services/generator.py` `CATEGORY_CATALOG` (+`other`) |
| Vapi + Retell import & live transport | ✅ | `importers/{vapi,retell}.py`, `transport/{vapi_ws,retell}.py` |
| Rule-based assertions (includes/excludes/patterns) | ✅ | `eval/rules.py`, `models.RuleCheck` |
| LLM judge (pass/fail + reason + suggestions) | ✅ | `eval/judge.py` |
| Meta/contract check (`--strict` → inconclusive) | ✅ | `eval/meta.py` |
| Beats + phases test agent | ✅ | `agent/orchestrator.py`, `agent/beats.py`, `models.Beat/Scenario` |
| CLI (import/suite/simulate/report/export/ui) | ✅ | `cli/*.py` |
| MCP surface | ✅ | `mcp/server.py` |
| Local UI (onboarding, agents, suites, evaluations, batch) | ✅ | `ui/src/pages/*` |
| Simulation artifact + regression report | ✅ | `models.SimulationArtifact`, `cli/report_cmd.py` |
| Wide STT/TTS provider catalog (incl. pyai default) | ✅ | `providers/catalog.py` |

---

## 2. PARTIAL (exists but diverges from spec)

| BUILD-SPEC area | State | Gap to close |
|---|---|---|
| **Generation** | Template-based, not LLM | No LLM call, no agent-config input, **no prompt-aware** (D2), no validation stage, no stop-word linter, no C2 citation enforcement, no `publishable`, no `generation_job` |
| **Adapter contract** | `connect/send_text/receive/hangup` (text-level) | Spec wants `connect/send_audio/recv/teardown` (PCM) + 8 declared ops w/ `Unsupported` sentinel; voice exists but higher-level via vapi_ws/LiveKit |
| **Judge** | LiteLLM, single | Not **blinded** (self-preference), no seed/temp in a run record, no κ calibration |
| **Agent import** | AgentGraph IR (data only) | No `agent_config_version` snapshot, no `prompt_sha256`/drift, no goal extraction, no `prompt_access` policy |
| **Report** | text/regression report | No SVG **card**, no **badge**, no grade from stored scores, no framing line |
| **Live view** | UI Batch/Evaluations pages | No SSE 3-event grid w/ `error_kind` colours; check if streaming at all |
| **Categories as data** | Python dict | Spec wants `test_category` rows (weights, is_control, requires_citation) |

---

## 3. MISSING (not built at all)

**Foundations**
- SQLite + the entire 20-table schema (§3). Code is file-based.
- Migration runner / `PRAGMA user_version` / `db reset` (§3.7).
- Single bounded writer queue (§2 backpressure).

**Determinism & the headline claim**
- SHA-256 caller-audio cache, `caller_audio_set_sha256`, `wiretap verify` (F1).
- PCM RX/TX reactive spine, RMS turn detection, barge-in, hangover bias (F6/F7/F13/F14).
- `wire_event` + `payload_blob` content addressing (F12).
- Ground-truth STT diff (`turn_transcript.source='ground_truth'`).

**Scoring**
- `run_score` materialized + `scorer_version` (F5); composite formula (§6).
- `assertion_result` numeric `score`/`label`/`weight`/`evidence_source` (F5/F10).

**Safety (the whole differentiator #5)**
- `attestation` (ownership etc.), 8 pre-flight gates (§8), ToS registry, irreversible-tool blocking + mock webhook server, `redact.py` denylist (incl. system-prompt leak, F12).

**Cost**
- `pricing.yaml`, BudgetGovernor, cost columns + settlement poll (§7, F11).

**Corpus & authoring**
- The 50 cited techniques (`TECHNIQUE-CATALOGUE.md`), seeded to `test_case`.
- Immutable `suite`/`suite_version`/`suite_test`, content hashes, staging→review→finalize.

**Ops verbs**
- `verify`, `rebuild --dry-run`, `run --resume`, `reap`, `prune`, `doctor`.

**Loopback / demo**
- `local-demo` fixture transport (BUILD-SPEC's hour-1 P0). Code has a text "stub" but not the fixture transport that fakes half-open sockets / 0xFFFFFFFF WAV / 9KB-prompt frames.

**Leaderboard / CI** — signed `result.json`, GitHub Action, PR comment (PROJECT.md marks these a **non-goal**, so this is a philosophy conflict, not just missing work).

---

## 4. Reconciliation — recommendation

The code is a genuine working slice of the same idea and should not be thrown away. But BUILD-SPEC's foundations (SQLite, PCM determinism, safety gates, cost) are exactly the parts that make Wiretap defensible (§7.3 of the research) — and they're the parts not built. Suggested path:

**Keep the code as the base. Layer the differentiators in this order** (each is a BUILD-SPEC phase mapped onto what exists):

1. **Decide the storage fork first.** Everything downstream (run_score, verify, versioning) needs SQLite. Either adopt it (big, but unblocks the differentiators) or consciously stay file-based and cut the claims that need it (determinism-verify, versioned scoring, resume). *This is the pivotal call.*
2. **Upgrade generation** from templates → LLM + prompt-aware + validation + the 50-technique catalogue. High product value, moderate effort, reuses the existing 7-category structure.
3. **Add the safety layer** (attestation + pre-flight gates + redact). This is the legal/positioning moat and is entirely absent.
4. **Add determinism + verify** (SHA audio cache, PCM spine, `verify`) — only meaningful once storage is decided.
5. **Card + badge + cost**, then leaderboard/CI **only if** the PROJECT.md non-goal is reversed (D9 says reverse it).

**Two conflicts to resolve explicitly, because the code already took the opposite stance:**
- **CI/leaderboard**: PROJECT.md non-goal vs D9 in-scope. D9 wins per V1-SCOPE, but the code was written the other way.
- **License**: code is Apache-2.0; wiretap-docs assumed MIT. Pick one.
