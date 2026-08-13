# Wiretap × LangWatch — Research and Architecture Alignment

**Version:** draft 2 · **Date:** 2026-08-12 · **Supersedes:** draft 1 (same filename, filed as `wiretap-docs/LANGWATCH-RESEARCH.md`)
**Why a draft 2:** draft 1 was written without `REVIEW-FINDINGS.md` (2026-08-11) and without `SUITE-LIFECYCLE.md` (2026-08-10). Both change conclusions, not just details. Draft 1 predicted this blind spot in its own §0.5 item 8 and was wrong in exactly the way it predicted.

> **The governing principle, unchanged.**
> **Wiretap's own docs define WHAT we build. LangWatch tells us HOW a mature system solved adjacent problems.**
> Wiretap docs → source of truth for scope. LangWatch → source of proven patterns. Our engineering judgment → the implementation.
> No LangWatch feature enters Wiretap's scope unless a Wiretap document already asked for it.

---

## §0. Provenance, method, and what changed

### 0.1 Wiretap sources (authority order, per `wiretap-docs/README.md`)

| ID | Document | Date | Authority | Used here for |
|---|---|---|---|---|
| **W0** | `REVIEW-FINDINGS.md` | 2026-08-11 | **Highest** — corrections to W1 | 18 defects (F1–F18), the ordered cut list (16 tables → 8), 11 missing items, the riskiest assumption |
| **W1** | `ARCHITECTURE.md` | 2026-08-10 | High — live-verified | Vendor matrix, audio pipeline, determinism, execution model, 16-table runtime schema, adapter contract, measured economics |
| **W2** | `SUITE-LIFECYCLE.md` | 2026-08-10 | High — proposal | **The authoring layer**: agent import → config snapshot → goal extraction → test generation → suite → suite list. 10 further tables, C1–C3, E1–E8, S1–S4 |
| **W3** | `PRD-STALE.md` | 2026-08-05 | **Superseded** | Goals, non-goals, personas, safety/legal requirements, verification gates — with 13 known-false claims (W1 §3.1) |
| **W4** | `probes/` | 2026-08-10 | Executable | Source of every ✅ in W1 |
| — | *This document* | 2026-08-12 | Reference | LangWatch research + mapping + architecture proposals |

**Authority rule I have applied throughout:** W0 > W1 > W2 > W3. Where W0 cuts something W1 specifies, I treat it as cut and say so. Where W2 adds something W3 called a non-goal, I treat it as scoped and say so.

### 0.2 LangWatch sources

Retrieved 2026-08-12: `langwatch/langwatch` repo + releases; `langwatch/scenario` README; `langwatch.ai/docs` — introduction, concepts, observability overview, trace-vs-activity ingestion, Python integration guide, evaluations overview, evaluators list, custom scoring, experiments overview, multimodal evaluation, datasets overview, **AI dataset generation**, annotations, AI gateway overview, **prompt-management data model**, self-hosting overview + infrastructure/architecture + licensing + ops console, the full `llms.txt` API index, changelog, pricing, trust center; the "Testing Voice Agents with Scenario in Real Time" post. Full list in Appendix A.

### 0.3 Labelling

**[CONF-L]** confirmed LangWatch behavior (their docs/repo) · **[INF-L]** my inference about LangWatch, never to be cited as fact · **[REC-W]** recommendation for Wiretap, tagged **A** (required by a Wiretap doc) / **B** (inspired by LangWatch) / **C** (my proposal, not in any Wiretap doc) · **[GAP]** information Wiretap needs that no Wiretap doc contains · **[Δ1]** changed from draft 1.

### 0.4 What draft 1 got wrong — five withdrawals and reversals

Read this before reusing anything from draft 1. Each of these is a *conclusion* change, not a wording fix.

| # | Draft 1 said | Corrected | Cause |
|---|---|---|---|
| **Δ1** | "Test/scenario generation is **deliberately out of scope — do not treat as a gap**" (§0.5) | **Generation is scoped.** W2 specifies a five-stage pipeline, 10 tables, an HTTP surface, and a UI flow. Whether it lands in the 33-hour window is open decision **S1** — that is a scheduling question, not a scope question | W2 was not in context |
| **Δ2** | "Card/report as **pure projections** recomputed at render time" (rec #2, §5.3) | **Scores must be materialized** into `run_score` with `scorer_version` at scoring time. The renderer is pure over `run_score`, not over `assertion_result` | **F5**: recompute-at-render means changing the scorer silently changes every historical grade |
| **Δ3** | "Add `export_run` / `export_assertion` **views**" (rec #5, §5.6) | **Withdrawn.** Drop the view mechanism entirely; one serializer module + a frozen-keyset test | **F8**: a view cannot carry the timeline's five tables, and a view is the wrong mechanism |
| **Δ4** | "Persona corpus stays YAML in the repo; a DB-backed dataset **adds no value**" (§5.8) | **Reversed.** `test_case` must be a table. Generated, per-agent cases cannot live in a shared repo pack, and the card's category/tier rollups have no source without it | **F4** + W2 §3.1 |
| **Δ5** | "`mode='observed'` run-of-one: **Adopt**" (§5.10, mapping #20) | **Downgraded to Future (v1.3).** Cut it now; it is the sole reason `persona_id` is nullable, which makes F3's UNIQUE constraint vacuous | **F3** + W0 cut #13 |

Two further corrections of *fact*, both mine:

- **Δ6** — draft 1 said "16 tables." The set is **26**: 16 runtime (W1 §8) + 10 authoring (W2 §3.1). After W0's cut list the runtime side is **8–10**, so the realistic v1 total is 8–10, or 18–20 if S1 lands the authoring layer.
- **Δ7** — draft 1 §5.1 recommended **skipping** an `agent` table for v1. Reversed: even with generation deferred, `agent` + `agent_config_version` are needed for two things W1 §9.1 already requires — the persona stop-word linter (Vapi `endCallPhrases`, Retell `end_call`) and per-agent latency-config comparability.

Draft 1's §0.4 correction (that `langwatch/scenario` does voice first-class, so W3 §1's "no OSS tool does duplex audio" wedge is false) **stands and is unchanged**. It is restated in §7.3 because it is still the most consequential competitive fact in the set.

### 0.5 What is still missing — do not fill these in from LangWatch

| # | Missing | Impact | Status |
|---|---|---|---|
| 1 | **S1: is the authoring layer in the 33-hour build or v1.1?** | 10 tables, ~16–52 h, and whether §4 of W2 is built at all | W2 §9 S1; README open decision 1 |
| 2 | **Composite score formula, GitHub Action, PR comment + delta vs base, percentile-vs-distribution** | The card headline and the entire CI story | Answered in conversation, never written down |
| 3 | **Vapi prompt exposure** — hash-and-discard or restate the trust claim | Public trust claim | W1 §3.1; W2 §2 C1 proposes `prompt_access ∈ none\|transient\|stored` as the resolution — needs a yes |
| 4 | **Audio-native judge in v1** or keep the v1.2 deferral | Judge surface area | W3 §2.2 vs the conversation |
| 5 | **`unclear` handling in the κ computation** | A published number | W3 §9.4 requires class balance; the rule is unstated. Note W0 cut #4 removes `dispute` from v1 anyway |
| 6 | **Retell in or out** (WebRTC cost + ToS prohibition) | ~8–12 h | W1 §10 Q1; W0 cut #1 says out |
| 7 | **Two probes that decide unfixable things**: does `vapi.websocket` queue silently? does a 3-beat reactive spine complete against a real agent? | The 50-tile grid's honesty and every latency number; F6's lost-wakeup | W0 "Riskiest assumption" + README. ~30 min, ~$0.25, mostly written |
| 8 | **S2**: standard corpus as YAML pack or seeded `test_case` rows | Whether `core-50@v1` and generated suites share one code path | W2 §9 S2 — I give a recommendation in §5.8, tagged **C** |
| 9 | **S3/S4**: goal-extraction quality under `prompt_access='none'`; ownership of the generation prompt template | Whether Retell users get a degraded product; C2's safety enforcement | W2 §9 |
| 10 | **Who writes the 50 personas, and when** | Critical path for both the grid and the card | W0 "Missing entirely" |
| 11 | **Schema migrations** — no `PRAGMA user_version`, no runner, no `db reset` | Two engineers editing a shared `./data/wiretap.db` diverge by hour six | W0 "Missing entirely" |

---

# PART 1 — LangWatch capability research

Structure per capability: **problem → workflow → entities/data model → interaction → implementability → Wiretap relevance.** Relevance is a judgment; §4 makes the commitments.

## 1.1 Observability and tracing

**Problem.** An agent run is a tree of LLM calls, tool calls and retrievals; the final output does not say which step failed.

**Workflow** [CONF-L]. `langwatch.setup()` → `@langwatch.trace()` on the entrypoint → spans on inner steps (decorator or auto-instrumentation) → read the waterfall in the UI.

**Data model** [CONF-L] — six identifiers carry the whole model:

| Concept | Field | Their definition |
|---|---|---|
| Thread | `thread_id` | "The entire journey a user takes in a single session" |
| Trace | `trace_id` | "A single, complete task… no matter how many internal steps it takes" |
| Span | `span_id` | "pinpoints a specific action taken by your system or an LLM call" |
| End user | `user_id` | "Identifies the actual end-user interacting with your product" |
| Customer | `customer_id` | Per-tenant attribution for platform builders |
| Labels | `labels` | Free tags on traces; used for version tracking and experiment comparison |

Span types are a semantic enum (`llm`, `rag`, `tool`, `agent`, …) with rendering consequences; `span.update(contexts=[…])` attaches retrieved documents. Views: waterfall, flame graph, topology map, sequence diagram. OTel/OTLP with GenAI conventions; Python/TypeScript/Go SDKs + Java integration + ~25 framework integrations. [all CONF-L]

**Interaction** [CONF-L]. SDK → OTLP → App `POST /api/otel/v1/traces` → Redis queue → workers → ClickHouse projections → UI reads projections + SSE.

**Wiretap relevance.** `run → call → turn` is the same shape one level up. The transplantable item is **typed event kinds with rendering consequences** — W1's `wire_event.kind` is free text today, and F12 shows what free-text payloads cost (14 MB of duplicated system prompt per run). See §5.4.

## 1.2 Spans, generations, tool calls, RAG

**Confirmed** [CONF-L]. Per-SDK tutorials for capturing input/output, RAG contexts, metadata, **LLM costs**, **time-to-first-token**, **tool calls**, **conversations**. Cost enrichment is a *pipeline stage* emitting a `CostEnriched` event — the server derives money from client-supplied usage.

**Implementability.** Server-side derivation means a price-table fix retroactively corrects history, *provided* the raw events survive. [INF-L: they document projection replay generally; they do not state that cost is recomputed that way.]

**Wiretap relevance.** W1's `cost_ledger` has `basis ∈ {reported, derived}` and `rate_source`, one step from replayable — but **F11** shows the schema currently forbids the state that actually occurs (Vapi reports `cost: 0, status: in-progress` at teardown while `amount_usd` is `REAL NOT NULL`), and **W0 cut #10** collapses the ledger to four columns on `run`. The surviving recommendation is one column, not a redesign: §5.9.

## 1.3 Conversation and session tracking

**Confirmed** [CONF-L]. `thread_id` groups traces into a session; **"Evaluation by Thread"** is a documented online-evaluation mode — the evaluated unit can be the whole conversation.

**Wiretap relevance.** Confirms that call-level and turn-level assertions need distinct code paths, which W1 already has (`assertion_result.evidence_turn` nullable). **F10** adds that evidence must also name *which transcript* it indexes (`turn_transcript` holds up to four rows per turn) — a defect LangWatch does not have because they store one text per span.

## 1.4 Agent execution tracking and behavior analysis

**Confirmed** [CONF-L]. Multi-agent runs render as waterfalls, flame graphs, topology maps and sequence diagrams. **`agents` is a first-class CRUD API** — agents are stored entities, not metadata strings. A separate coding-agents API tracks PR-level usage and session events with spend attribution.

**Wiretap relevance.** **[Δ7]** Draft 1 called agent-as-entity a skippable convenience. W2 §3.1 makes it required (`agent`, `agent_config_version`, `UNIQUE (vendor, external_id)` so re-import is idempotent), and W1 §9.1's own requirements — record the target's stop words, record per-agent latency config — have nowhere else to live. Topology/sequence views remain over-engineering: a Wiretap call has two participants, and the combined dual-tinted waveform (W3 §12.3) is a strictly better instrument.

## 1.5 Evaluations: the evaluator registry

**Workflow** [CONF-L]. Choose a built-in evaluator by slug (`ragas/faithfulness`), configure it, then run it offline in an experiment, online over sampled traffic, or inline as a guardrail. Evaluator configs are CRUD entities; "saved evaluators" are named configured instances reusable across surfaces.

**Catalogue** [CONF-L]: *Expected answer* — Exact Match, LLM Answer Match, LLM Factual Match, BLEU, ROUGE, SQL Query Equivalence, Semantic Similarity. *LLM-as-judge* — Boolean, Category, Score, Rubrics-Based Scoring, Custom Basic, Summarization Score. *RAG* — RAGAS Faithfulness, RAGAS Response Context Precision/Recall, RAGAS Response Relevancy, Context F1/Precision/Recall. *Quality* — Lingua Language Detection, Valid Format, Off Topic, Query Resolution. *Safety* — Azure Content Safety, Azure Jailbreak Detection, Azure Prompt Shield, OpenAI Moderation, Presidio PII Detection, Competitor Blocklist/Allowlist/LLM Check. Executed by a separate service, **LangEvals (5562)**. v3.11.0 removed legacy Ragas evaluators as a breaking change.

**The custom-scoring contract** [CONF-L] — the most transplantable API in LangWatch:

```python
langwatch.get_current_span().add_evaluation(
    name="…",      # required — identifier shown in the UI
    score=0.0,     # numeric, typically 0–1
    passed=True,   # boolean
    label="…",     # category
    details="…",   # human-readable explanation
)
```
> "At least one of `passed`, `score`, or `label` should be provided."

**No registration step** — you run your own logic and report the result. Also via `experiment.log()` and a REST collector.

**Wiretap relevance.** High, and now *reinforced* rather than merely forward-looking: **F5** requires stored scores with weights, which means `assertion_result` needs a numeric channel regardless of the v1.2 judge panel. Two nullable columns. See §5.7.

## 1.6 Experiments (offline / batch)

**Confirmed** [CONF-L]. An experiment is **a dataset + a target + scoring functions**. API: create, list, **run**, list runs, **poll a run**, **read run results**, report DSPy optimizer steps. UI or SDK. Documented for CI/CD gates. `ExperimentRuns` is a named ClickHouse projection.

**Data model** [INF-L]. `Experiment` (definition) → `ExperimentRun` (execution) → per-record results.

**Wiretap relevance.** **[Δ]** Draft 1 rejected the definition/execution split because content hashes gave comparability. W2 §2 C3 *introduces exactly that split*: `suite` (identity) → `suite_version` (immutable definition) → `run` (execution). So the pattern is now adopted — by Wiretap's own design, arrived at independently. The remaining borrow is the **job/poll pattern** for long-running generation: W2 §5.2's `POST …:generate → 202 + generation_job id → progress over SSE` is LangWatch's run-then-poll shape, and their status enum (`running|succeeded|failed|partial`) matches `generation_job.status` exactly. Convergence worth trusting.

## 1.7 Online evaluation, monitors, guardrails

**Confirmed** [CONF-L]. Three modes: online evaluation over sampled traffic (monitors are CRUD entities with a toggle), guardrails (inline allow/block/modify, dedicated endpoint), triggers/alerts (incl. Slack; CronJob every ~3 min).

**Wiretap relevance.** Low by scope — no production traffic in v1, never in the request path. The borrowable idea is that **blocking-ness is a property of the binding, not of the evaluator**, which is W3 §9.2's `blocking`/`advisory` split generalized. Independent convergence; keep the flag, do not build three execution contexts.

## 1.8 Agent simulations — Scenario (the closest analogue)

**Confirmed** [CONF-L]. Roles: `USER` (simulator), `AGENT` (under test, one `call()` method), `JUDGE` (verdict + reasoning). Scripted → autonomous continuum. Runs under pytest/vitest. Python, TypeScript, Go. **Voice is first-class:** *"Scenario treats voice as a first-class citizen: same `scenario.run()` entrypoint, same script DSL, same judge — only the medium changes."* Shipped adapters: ElevenLabs (hosted Conversational AI + composable STT/LLM/TTS), OpenAI Realtime (model-as-agent and model-as-user-simulator); Twilio Media Streams, Pipecat WebSocket and Gemini Live referenced. `scenario.audio()` injects recorded clips; `scenario.background_noise()` and bundled effects; **`scenario.interrupt()`**; **`result.latency` = TTFB + p50 + p95**; `ffmpeg`/`webrtcvad`/`websockets` are hard deps; `RealtimeAgentAdapter` / `RealtimeUserSimulatorAgent`; CI-safe because "the simulator and agent exchange audio frames as data." TypeScript leads; Python realtime is "coming soon."

**The event protocol** [CONF-L] — three types to `POST /api/scenario-events`:

| Event | Payload |
|---|---|
| `SCENARIO_RUN_STARTED` | `metadata` with `name`, `description` |
| `SCENARIO_MESSAGE_SNAPSHOT` | `messages[]` — user/agent/tool exchanges |
| `SCENARIO_RUN_FINISHED` | `status ∈ {SUCCESS, FAILED, ERROR}`; `results` with `verdict`, `reasoning`, `metCriteria[]`, `unmetCriteria[]` |

Shared fields on every event: `type`, `timestamp` (Unix ms), `batchRunId`, `scenarioId`, `scenarioRunId`, `scenarioSetId` (default `"default"`).
Server entities: **Scenarios** (CRUD + archive), **Suites** (CRUD, **duplicate**, **trigger run**, archive), **Simulation Runs** (list, batch summaries, get), **Scenario Events**.

**[INF-L]** `scenarioSetId` = the suite, `batchRunId` = one suite execution, `scenarioRunId` = one scenario's execution. Three-level identity with the *set* as the versioned unit.

**Wiretap relevance — two directions, both stronger than in draft 1.**
1. **Pattern.** The event triple maps onto Wiretap 1:1 (`batchRunId ≈ run.id`, `scenarioSetId ≈ suite_version_id`, `scenarioId ≈ test_case.id`, `scenarioRunId ≈ call.id`) and their `results` shape maps onto `verdict` + `judge_critique` + blocking/advisory rows. Their `status ∈ SUCCESS|FAILED|ERROR` is also the seed of the **error taxonomy W0 lists as missing entirely** — see §5.4.
2. **Suites API shape.** LangWatch's Suites endpoints (list/get/update/**duplicate**/**trigger run**/archive) are nearly identical to W2 §5.2's routes, including duplicate. Draft 1 said "no CRUD API in a local tool"; W2 defines one, so this flips to **Adapt**.

## 1.9 Datasets — now directly relevant **[Δ4]**

**Confirmed** [CONF-L]. Spreadsheet-like entities with managed **columns and data types**; populated by manual entry, **batch import from traces**, CSV/JSONL upload with column mapping, **continuous production capture via automations**, **AI generation**, or SDK/MCP. Support **versioning and staging**; track **provenance from production traces**; feed experiments. API includes `update-staging`, `action-upload`, **`action-finalize`**, `action-retry`, plus direct browser→S3 upload.

**Interaction** [CONF-L]. Traces → (annotation or automation) → dataset → experiment → results: the observe→testcase loop is a first-class product path.

**Wiretap relevance.** Draft 1 said the persona corpus should stay YAML and a DB-backed dataset "adds no value." That was wrong on both counts:
- **F4**: without a `test_case`/`persona` table, the card's per-category and per-tier rollups have no source, and once a YAML file changes, old runs become un-rollup-able.
- **W2**: generated cases are per-agent, non-shareable, and immutable-by-version. They cannot live in a shared repo pack.

So LangWatch's dataset model is now the relevant reference, and the specific mechanism worth taking is **staging → review → finalize**, which W2's pipeline lacks between stages 4 and 5. See §5.8.

## 1.10 Human evaluation — annotations

**Confirmed** [CONF-L]. Annotate a message with comment/link/arbitrary info. **Queues** with name, description, assigned members; annotators work a backlog and click "Done". **Custom score fields** are typed: **checkbox** (multi-select) or **multiple choice** (single-select), each optionally with reasoning, admin-activated. Full annotations API. How annotations feed datasets is **not documented** — do not assume.

**Wiretap relevance.** Reduced. W0 cut #4 removes `dispute` + tune/holdout splits from v1 entirely. If it returns (v1.2, alongside the N≥100 calibration study), the transplantable part is **typed single-select labels + separate reasoning**, because κ is computable only over a closed label set — and the `unclear` rule (§0.5 item 5) has to be documented at that time.

## 1.11 Metrics, scoring, analytics, dashboards

**Confirmed** [CONF-L]. `Analytics` and `Topics` are ClickHouse projections. Dashboards API (list/create/get/reorder/rename/delete), Graphs API (CRUD), analytics timeseries API, embeddable dashboards, daily topic clustering via CronJob.

**Wiretap relevance.** Still one of the clearest rejects — *and now for a second reason*. W3 §8.1 requires that no average or grade can render on a non-complete run; a user-composable aggregation surface is a hole in that guarantee. **F5** adds the deeper point: Wiretap's scoring must be *stored and versioned*, not computed on the fly by a flexible query layer. A dashboard builder is the opposite of what F5 requires.

## 1.12 Cost and token tracking

**Confirmed** [CONF-L]. `CostEnriched` as a pipeline stage; per-SDK cost/TTFT tutorials; gateway attributes per-request cost and cache-hit status per tenant with hierarchical budgets (org→team→project→user), soft-warn or hard-block.

**Wiretap relevance.** The hierarchy is irrelevant. Two things survive: (1) cost derived from stored raw facts, so a corrected price table is retroactive — §5.9; (2) the soft/hard vocabulary. Wiretap remains **ahead** on provenance (`pricing.yaml` with mandatory `verified_on` + source; W3 §14.4 verified that no vendor dates its published rates) and is now **behind its own spec** on settlement: **F11** — Vapi reports `cost: 0, in-progress` at teardown, and PyAI `/v1/me` credit does not move in real time, so **BudgetGovernor has no real-time spend signal from either vendor and is necessarily estimating**. W1 §6.2's overshoot formula (`budget + concurrency × per_call_max`) is the only real guarantee and must be stated as such.

## 1.13 Latency tracking

**Confirmed** [CONF-L]. TTFT tutorials; span durations as the latency unit; Scenario's `result.latency` = TTFB + p50 + p95.

**Wiretap relevance.** Wiretap's four client-measured anchors + `latency_valid` + `measured_at_concurrency` remain a stronger instrument than TTFB/p50/p95 with no validity flag — **but F14 removes the right to be smug**: `agent_speech_end` fires 250 ms after audio stops and onset is quantized to 20 ms windows, so every harness number carries a fixed **+250 ms bias** and ~20 ms quantization that is currently unrecorded. Fix (F14): store `rms_threshold` and `hangover_ms` on `run`, subtract the hangover when stamping `turn.t_end_ms`, and print the quantization floor next to any p95. **F2** compounds it: three different clock bases feed one timeline and are never reconciled. Do not publish a latency number until F2 and F14 are applied.

## 1.14 Model and provider tracking

**Confirmed** [CONF-L]. Model Providers API, Secrets API, custom models, gateway virtual keys (`vk-lw-<ulid>`) as revocable scoped credentials.

**Wiretap relevance.** Low. Keys in keyring/`.env` with `wiretap doctor` warning on tracked files is stronger by simplicity. The one conceptual borrow: a **capability-scoped credential** is the right frame for W3 §15.4's rule that sandbox keys cannot drive third-party adapters.

## 1.15 Prompt and version tracking — the pattern that validates C3

**Confirmed** [CONF-L]. Full prompt product: versions, tags (`prompt:tag`), GitHub sync, link-to-traces, playground, A/B, DSPy optimization. And the **data model**, which is the part that matters here: a `Prompt` entity (`id`, `handle`, `projectId`/`organizationId`, `scope ∈ {PROJECT, ORGANIZATION}`) plus **immutable Version snapshots** (`version` numeric counter, `versionId`, `createdAt`/`updatedAt`, `authorId`); *"Changing parameters creates a new prompt version"*; `parameters` is an "arbitrary JSON object versioned alongside the prompt"; `deletedAt` for soft deletion.

**Wiretap relevance.** Prompt *management* remains out of scope. But the **entity + immutable-version-snapshot + soft-delete** shape is exactly what W2 §3.1 built for `suite`/`suite_version` and `agent`/`agent_config_version`, independently. That convergence is the strongest available evidence that C3's decision — *any edit creates a new `suite_version`* — is right, and it supplies two small refinements Wiretap is missing: an **author field** on version rows (who regenerated this?) and **soft-delete over hard-delete** (W2 already uses `archived` on `agent`/`suite`; version rows have no equivalent).

Separately: **C1's `prompt_access ∈ none|transient|stored`** is a better answer than LangWatch has, because they never had to promise not to read it. F12's finding that Vapi ships the **full 9,304-char system prompt on every `conversation-update` frame** means the prompt leaks into `wire_event` payloads regardless of `prompt_access` — so C1's policy and F12's denylist extension are the same requirement seen from two sides. Both must be applied together (§5.6).

## 1.16 Debugging and error analysis — the Ops Console

**Confirmed** [CONF-L], four tools:

| Tool | What it does | Their stated reason |
|---|---|---|
| **Queue Management** | Inspect error groups, unblock stuck queues, drain, reprocess from the DLQ | Processing gets blocked by errors needing intervention without DB access |
| **Projection Replay** | Replay events from ClickHouse to rebuild derived data; bulk or per-aggregate; **dry-run first** | A code change can break how projections compute state |
| **Deja View** | Time-travel: full event history for an aggregate; reconstruct any projection's state at any moment | Debug complex state by seeing how events unfolded |
| **The Foundry** | Build **synthetic traces**, visualize them, send them to a project without touching production | Validate the pipeline handles edge cases before real traces arrive |

**Wiretap relevance — the highest-value section, and W0 agrees independently.**
- **The Foundry ↔ the loopback/fixture transport.** W0's "Missing entirely" opens with *"`local-demo` loopback adapter as hour-1 work, not a footnote"*; README records that the probe work, the staff review and this research converged on it without coordination. Upgraded from "borrow #1" to **P0, hour 1**.
- **Projection Replay ↔ `wiretap rebuild`** — but reconciled with **F5**: replay must *write versioned score rows*, not silently recompute a grade. Their dry-run flag is worth copying verbatim. §5.3.
- **Deja View ↔ `wiretap replay <call>`** — W1's `wire_event` already is the history; F12's payload dedup is what keeps it affordable.
- **Queue Management → reject.** Wiretap's failure model is bounded retry then `not_executed`. But two adjacent gaps W0 names are real: **error taxonomy** (`call.status='error'` + free-text `retry_reason`, no enum) and **backpressure** (writer queue, event bus and RX buffer all unbounded). LangWatch's answer to both is a bounded queue with inspectable error groups; Wiretap's is an enum plus a bounded queue that drops `wire_event` first. §5.5.

## 1.17 Extensibility, packaging, licensing

**Confirmed** [CONF-L]. Built-in **MCP server with OAuth**; **Agent Skills** (`npx skills add langwatch/skills/level-up`; skills for tracing, evaluations, scenarios, prompts); **agent-plugin v1.0.0** for Claude Code (2026-08-10); prompts CLI; three SDKs; ~25 integrations; n8n/Langflow/Flowise. Apache-2.0 core + `ee/`; **unlicensed self-hosting keeps the entire product surface with unlimited users and volume**; a key gates only SSO, RBAC, SCIM, audit logs, gateway webhooks, AI governance, extended retention, support. `LANGWATCH_LICENSE_KEY`; expiry doesn't disable features.

**Wiretap relevance.** MIT, no tiers — licensing not required. MCP is in W3 §13 (six tools) but **W0 cut #14 removes the MCP surface from v1**: ship CLI and UI. Agent Skills as a distribution path stays a post-v1 idea.

## 1.18 Governance ingestion (two endpoints, one pipeline)

**Confirmed** [CONF-L]. `POST /api/otel/v1/traces` (project key; systems you own) and `POST /api/ingest/otel/:sourceId` (org-admin `IngestionSource` secret; external platforms) — *"Both endpoints feed the same internal pipeline and storage, differentiated only by authentication scope and tenancy model."*

**Wiretap relevance.** **[Δ5]** The principle is the right long-run shape for W3 §16.3's production-ingest-as-run-of-one, but **F3 + W0 cut #13 remove `mode='observed'` from v1**, because the nullable `persona_id` it requires makes F3's UNIQUE constraint vacuous. Re-add in v1.3 as a *source adapter* emitting the same `turn`/`wire_event` rows, with a `run_source` column instead of a nullable FK. **Future**, not now.

## 1.19 AI dataset generation — newly relevant **[Δ1]**

**Problem.** Nobody has an evaluation dataset on day one.

**Confirmed** [CONF-L]. A built-in AI data generator inside the **Evaluation Wizard**, explicitly aimed at "evaluations, regression tests, and **simulation-based agent testing**." The workflow is generate → **validate → human review before records are finalized**, and **generated records are marked and tracked to maintain provenance**. [The docs describe the shape; they do not publish the generator's prompt, its rejection taxonomy, or per-record provenance field names — treat those as unknown, not inferred.]

**Wiretap relevance.** W2 §4's five stages (extract → plan → generate → validate → assemble) are more rigorous than what LangWatch documents: the plan stage is deterministic, the generator is constrained to *instantiate a cited technique rather than invent one* (C2), and validation has eight named checks including a stop-word linter verified against real vendor behavior. Two things LangWatch has that W2 does not:

1. **A human review gate before records are finalized**, backed by real API verbs (`update-staging`, `action-finalize`, `action-retry`). W2 goes straight from validate to assemble, which means a generated suite becomes `suite_version` v1 before a human has seen it — and `publishable=0` is the only signal. §5.8 recommends inserting staging.
2. **A wizard**, i.e. generation presented as a guided flow rather than a button. W2 §6's agent-detail screen is already close; the borrow is only the ordering (goals → matrix → cost estimate → review → finalize).

---

# PART 2 — LangWatch architecture

## 2.1 Services [CONF-L]

| Component | Port | Role |
|---|---|---|
| **App** | 5560 | "The single external entry point for all traffic" — UI, REST + OTel ingestion, auth, SSE |
| **Workers** | — | Stateless pods, **same image**, entrypoint `pnpm start:workers`; consume BullMQ jobs from Redis; run the event-sourcing pipeline; horizontally scalable |
| **NLP** | 5561 | Optimization workflows, topic clustering, custom evaluators |
| **LangEvals** | 5562 | Built-in evaluator library |
| **AI Gateway** | — | Go (chi, in-process JWT, embedded Bifrost); ~11 µs overhead at 5k RPS |

CronJobs: daily topic clustering, alert evaluation every ~3 min. Only the App is externally exposed; everything else is `ClusterIP`.

## 2.2 Storage [CONF-L]

**PostgreSQL** = control plane (users, teams, projects, configurations, prompt versions, evaluator definitions). **ClickHouse** = data plane (traces, spans, evaluations, experiments), tiered hot-SSD → S3 after a configurable TTL. **Redis** = BullMQ queue, cache, sessions. **S3** = cold storage, backups, externalized object content. v3.0 (2026-04-08) replaced Elasticsearch with ClickHouse and introduced event sourcing. Dev Helm install ≈ 2.6 CPU / 6.7 GiB.

## 2.3 The pipeline [CONF-L]

Each stage reads from the queue, processes independently, writes to ClickHouse:

1. **Ingestion & enrichment** — span ingestion, trace summarization, LLM cost enrichment, metric processing, embedding extraction, **PII redaction**
2. **Evaluation** — evaluation execution, annotation processing, experiment processing
3. **Reactions** — topic generation, automations/triggers, UI broadcasts

Outputs: **Events** (immutable: `SpanIngested`, `TraceSummarised`, `CostEnriched`, …), **Projections** (derived: Traces, Spans, Evaluations, ExperimentRuns, Analytics, Topics), **Reactions** (SSE, alerts, dataset appends).

**[INF-L]** The aggregate is probably the trace; projections are probably tenant-keyed ClickHouse materializations. Not stated by them.

**Two facts to internalize** [CONF-L]. **PII redaction happens before data lands in queryable storage** — the same boundary W3 §15.3 specifies (though F9 argues the Wiretap implementation of it should be cut for the window). **Evaluation is a pipeline stage, not a request handler** — scoring is asynchronous to capture by design, which is what W1 §6 already does by scoring after teardown.

## 2.4 Ingestion, APIs, frontend, versioning, extensibility

**Ingestion** [CONF-L]: OTLP/HTTP (protobuf, JSON, gzip, deflate, brotli); org-scoped bearer for governance; both converge on one pipeline.

**API nouns** [CONF-L]: traces (search/get/transcript/update-metadata/public-path), datasets, evaluators-config, evaluators, evaluations (run / namespaced / as-guardrail / report-batch), experiments, monitors, prompts, annotations, **scenarios**, **scenario-events**, **simulation-runs**, **suites**, **agents**, coding-agents, triggers, events, workflows, dashboards, graphs, analytics, secrets, model-providers, projects, teams, groups, organization, members, invites, roles, role-bindings, SCIM.

**Frontend/backend** [CONF-L]: Next.js app reading projections; **SSE** for live updates ("UI broadcasts" is a pipeline reaction); `Cmd+K` command bar.

**Versioning** [CONF-L]: prompts = immutable version snapshots + movable tags + GitHub sync + restore; datasets = versioning + staging; evaluator configs = entities; releases are semver with breaking changes called out (v3.11.0 removed evaluators and changed MCP auth).

**Extensibility** [CONF-L]: evaluators are config-as-data plus a separate execution service; custom evaluation needs **no registration**; integrations are OTel instrumentors; MCP/Skills/CLI all wrap the same REST API.

## 2.5 Recommended-for-Wiretap summary

| Pattern | Recommendation | Reconciled with |
|---|---|---|
| Immutable events + derived, **versioned** projections | **Adapt** — append-only tables + materialized `run_score` + `rebuild --dry-run` | **F5** (Δ2) |
| Same artifact, different entrypoint | **Inspired by** — one SDK, CLI + UI front doors | W0 cut #14 (MCP out) |
| PII redaction before storage | **Principle only** — F9 cuts the quarantine implementation for the window | **F9** |
| Evaluation async to capture | **Adopt** — already W1 §6 | — |
| Uniform evaluation-result contract | **Adapt** — `score`/`label` columns | **F5**, F10 |
| Three-event run protocol + `status ∈ SUCCESS/FAILED/ERROR` | **Adopt shape**, extend into the missing error taxonomy | W0 "Missing entirely" |
| Definition/execution split (`Experiment`→`Run`) | **Adopt** — `suite_version` → `run`, arrived at independently | W2 C3 |
| Entity + immutable version snapshot + soft delete + author | **Adopt** — validates `suite_version`, adds `authored_by` | W2 §3.1, 1.15 |
| Dataset staging → review → **finalize** | **Adapt** — insert between W2 stages 4 and 5 | W2 §4, 1.19 |
| Job + 202 + poll/SSE for long work | **Adopt** — `generation_job` | W2 §5.2 |
| Externalized/content-addressed large payloads | **Adapt** — `payload_blob(sha256, text)` | **F12** |
| Cost derived server-side, recomputable | **Adapt** — one column, `pricing_yaml_sha256` | **F11**, cut #10 |
| Synthetic-input playground (Foundry) | **Adopt** — loopback/fixture transport, **hour 1** | W0 "Missing entirely" |
| Ops actions as first-class verbs | **Adapt** — `rebuild`, `verify`, `reap`, `resume`, `prune` | **F1**, W0 |
| ClickHouse · Postgres · Redis/BullMQ · worker pods · NLP/LangEvals services · tiered S3 | **Reject** | W1 §2 (SQLite, one process) |
| Prompt management · DSPy · gateway · dashboards/graphs · monitors/triggers · annotation queues · RBAC/SSO/SCIM · multi-tenancy · licensing | **Reject or future** | §6 |

---

# PART 3 — The Wiretap specification, as extracted

Sourced from W0/W1/W2/W3 only. Nothing in this part comes from LangWatch.

## 3.1 Product goals (W3 §2.1, as amended by W1)

Five-minute first result with zero keys · reproducibility that survives a skeptic · vendor-neutral by construction (~200-line adapter) · cost as a first-class metric (two lines + cost per *resolved* call) · findings a developer can act on (failure pinned at a timestamp, audio playable there) · safe by default as blocking gates, not documentation · honest about its own accuracy (published judge/human agreement).

**W1 §5 narrows goal 2, and it matters:** the guarantee is an **identical caller-audio SHA-256 set**, *not* an identical score, because the agent under test varies run to run. Score stability becomes a *measured, published* per-suite number.
**W0 F1 then shows the narrowed claim is unqueryable:** `audio_artifact` is keyed only by `call_id`, `beat_cache` rows are shared across calls, `run.replication_sha256` hashes config rather than audio, and **no `wiretap verify` command exists anywhere**. Fix: `audio_artifact.run_id NOT NULL` + `run.caller_audio_set_sha256` computed at audio-prep time before the first dial, plus the verify verb. **The headline demo does not work until this is done.**

## 3.2 Non-goals (W3 §2.2), as amended

No SIP/PSTN/phone numbers · no hosted service or account · no leaderboard in v1 · no production monitoring in v1 · no audio-native judge in v1 · no inbound testing · no published exploit against a named vendor.

Two have moved: **"we do not read the system prompt"** is impossible as literally written on Vapi (W1 §3.1) and is replaced by W2 C1's `prompt_access` policy — pending decision. **"No auto-generated scenarios"** is reversed by W2 §4 — pending S1.

## 3.3 Personas and journeys (W3 §3)

**Priya** (voice-agent engineer, primary): find the embarrassing failure before a customer records it; hear the moment; same score twice; hard spend cap; CI gate; cost per resolved call. **Marco** (eng lead/buyer): run an identical suite against two of *his own* agents; methodology re-runnable; know the grader's accuracy. **Sam** (OSS contributor): adapter in an evening; persona as YAML in a PR; dispute a verdict. **Anti-persona**: someone attacking an agent they don't control — blocked structurally (enumeration proves control; sandbox keys can't drive third-party adapters; paste-by-id is demo-only).

## 3.4 Agent lifecycle — now a persisted flow (W2)

W3 §7.4 described connect → enumerate → pick. W2 makes it durable:

```
connect key → AgentImporter.list_agents() → upsert agent (UNIQUE vendor, external_id → idempotent re-import)
            → ConfigSnapshotter.snapshot() → agent_config_version (immutable; prompt handled per policy)
            → GoalExtractor.extract()      → agent_goal[]  (kind ∈ primary_task|constraint|policy|
                                                            escalation|capability|persona_trait)
```

`agent_config_version` stores the *parsed* config, not just a hash: model/voice/transcriber, language, `first_message`, **`end_call_phrases`** (the persona linter reads this), `tools_json` with an `irreversible` flag, `capabilities_json`, `latency_config_json`, `config_sha256`, `vendor_version`, and **`prompt_sha256` always recorded even when the prompt is not stored** — which is what makes "the prompt changed since this suite was generated" detectable under `prompt_access='none'`.

**C1 resolution** (W2 §2): `agent.prompt_access ∈ none | transient | stored`. `none` is the Retell default (config-only import; weaker tests, zero exposure — and the `factual` category is largely unavailable, a tradeoff to state *at the point of choice*). `transient` = in memory for generation, never written, enforced by the §8.8 denylist. `stored` = persisted in `agent_config_version.system_prompt`, requires an attestation row. The restated trust claim: *"your prompt is never transmitted to a third party except the judge/generator model you selected, and never persisted unless you choose `stored`."*

## 3.5 Test corpus, generation, and suites (W2 §3–§4)

**Categories as data, not an enum** — `test_category(id, display_name, description, default_weight, is_control, requires_citation)`, so a user pack adds a category without a migration, and a user-added category defaults to `requires_citation=1` (fail safe).

**`test_case`** carries `origin ∈ standard | generated | manual`, `category_id`, `difficulty_tier 1–5`, `beat_spine_json`, `assertions_json`, `requires_capability`, `expected_on_interrupt`, `citation`, `derived_from_standard_id`, `generation_job_id`, `agent_id` (NULL for the shared standard corpus), and **`fingerprint`** = sha256 over normalized beats + sorted assertions.

**C2 resolution** — generated adversarial/compliance cases have no citation of their own, so: the generator may only **instantiate a cited standard technique with agent-specific surface detail**, never invent an attack class; `derived_from_standard_id` preserves the citation chain; any suite version containing a `generated` member is `publishable = 0` and the publish path refuses it. This is what keeps W3 §15.11 (model-provider AUP) satisfied.

**C3 resolution** — reproducibility moves from the corpus to the suite version. `suite_version` is **immutable**; any edit creates a new version with `change_reason ∈ initial | regenerated | manual_edit | config_drift | imported`, `parent_version_id`, `content_sha256` over ordered member fingerprints, `test_count`, `publishable`. `wiretap compare` refuses across differing `suite_version_id` exactly as it refuses differing agent tuples. `suite_version.content_sha256` replaces `persona_set_sha256` in the replication bundle for generated suites.

**Five-stage pipeline** (W2 §4): **extract** (deterministic parse) → **plan** (deterministic target matrix: `targets[category] = round(total × weight / Σweights)`, with rules like "no tools → drop tool-invocation cases and redistribute to `factual`", "`language != en` → shift `linguistic` toward that locale's code-switch pairs", "irreversible tools present → force `operational` escalation cases") → **generate** (the only LLM stage, one call per cell or batched per category) → **validate** (8 checks: schema with ≥1 blocking assertion, **stop-word linter**, dedup by fingerprint, citation rule, safety class, capability subset, ≥1 goal mapping, beat count ≤ turn cap) → **assemble** (`suite_version` v1, ordered `suite_test` rows, `content_sha256`, publishability).

**Auto-naming**: `{AgentName} — {ConfigShortHash} — {N} tests — {YYYY-MM-DD}`, e.g. `Riley — a3f91c — 46 tests — 2026-08-10`; `name_source ∈ auto|user`.

**Eight edge cases** (W2 §8), all specified: E1 config drift (re-snapshot at open *and* pre-flight; amber state; run allowed but records `config_drift=1` and blocks comparison), E2 regeneration never mutates (three-way diff; **manually added tests carried forward by default** — "regeneration losing hand-written tests silently is the worst failure here"), E3 duplicate suites (name and content guards), E4 duplicate tests (fingerprint UNIQUE within a version; rejected-and-counted, not an error), E5 manual add/remove (`origin='manual'` sets `publishable=0`; removals are version-level, never deletes; disable ≠ remove; disabled tests count in "total" not "enabled" and record `not_executed`), E6 categories as rows, E7 **three independent version axes** (agent config / suite / **scorer**, all pinned on `run`, comparison refused unless all three match and naming which differs), E8 re-running (always targets a `suite_version_id`; caller audio from the SHA-256 cache so a re-run costs only the vendor meter; never overwrites prior results — which is what makes measured score stability computable).

## 3.6 Execution model (W1 §6–§7), with W0's defects marked

`pre-flight gates → suite resolution → audio prep → fan-out → per-call → aggregate`

**Eight blocking pre-flight gates** (W3 §8.2): keys valid · ownership attestation (verbatim, logged, never a config default, never env-bypassable) · smoke call · tool list shown + irreversible tools acknowledged · worst-case spend shown, confirmation above ~$5 · vendor-side spend cap attested · concurrency clamped to the live ceiling · capability filter applied with skipped tests listed *before* the run.

**Cache warm precedes the pool** — all caller audio synthesized before the first dial, so a TTS failure surfaces at second 3 instead of call 37, and the second run of a suite is nearly free.

**Per call, two coupled asyncio tasks** (W1 §6) — RX appends PCM and computes RMS, emitting `agent_speech_start|end`; TX awaits a named event, sleeps `delay_ms`, streams the cached WAV at 20 ms pacing. Reactive, not clock-scripted. Scoring entirely after teardown.

**Four W0 defects live here and none is cosmetic:**
- **F6 lost-wakeup deadlock.** If `agent_speech_end` fires while TX is inside `sleep()` or still streaming, the edge is lost and TX waits for an event that never comes; the call burns to the duration cap in silence and reads as an agent timeout. *Fix:* append-only event sequence with a TX cursor (`bus.wait_after(cursor, kind)`) plus a mandatory per-beat `timeout_ms` fallback stamping `turn.trigger='timeout'`. **Highest-frequency runtime bug in the design; invisible in code review.**
- **F7 the beat spine cannot express barge-in.** `beat.after` only ever waits on `agent_speech_end`, so an interrupter persona cannot speak *during* agent speech, `turn.interrupted` has no producer, and the nightmare archetype most likely to break an agent is unscriptable. *Fix:* `after ∈ {agent_speech_start, agent_speech_end, caller_beat_end}` + `after_ms`. ~10 lines.
- **F13 no behaviour on mid-beat socket death, and no read timeout.** Nothing says who cancels the peer task, writes terminal status, drains the writer queue, or releases the concurrency slot; half-open sockets (routine behind Cloudflare, which fronts Vapi) leave RX blocked forever; one hung call holds a slot permanently and the run never reaches `complete`, so **no grade renders at all**. *Fix:* one `asyncio.TaskGroup` per call, `ping_interval=5`/`ping_timeout=10`, a hard deadline task in the group, semaphore released in `finally`, terminal status written by the group owner.
- **F12 the real event-loop risk is not RMS.** Measured: pure-Python RMS is 8.6 µs/frame (0.43% of a core at 10 concurrent) and a simulated 20-call run held 20 ms pacing at p99 = 2.25 ms jitter. What actually breaks first: an unbounded writer queue behind a serialized SQLite writer, a blocking `fsync` stalling all pacers, and JSON-parsing Vapi's `conversation-update`, which carries the **full 9,304-char system prompt on every final transcript** — ~14 KB/frame, ~1,000 frames/run, **~14 MB of duplicated prompt** into `wire_event.payload_redacted`.

**Budget** (W3 §8.7 + W1 §6.2 + F11): four caps (dollars, minutes, per-call, hard `max_total_calls`), checked **between** calls, so the effective ceiling is `budget + (concurrency × per_call_max)`. Fails closed — unknown cost uses the `pricing.yaml` constant flagged `estimated`. **F11: there is no real-time spend signal from either vendor**; enforcement is an estimate and the overshoot formula is the only guarantee.

**Retry** (W3 §8.3, corrected): infra only, cap 2, budget-gated. PyAI concurrency rejects arrive as **HTTP 429 pre-upgrade** so the WS-close-`4429` branch never fires (**F16**: delete the dead enum value). On **Vapi** a 429 is a **~21 s opaque lockout with no headers**, so cap-2 retry burns both attempts inside it — treat as a 30 s cooldown.

**Rate vs concurrency vs dial-rate are three limits** (W1 §7) with a per-adapter `RateGovernor`. Concurrency is the real constraint (PyAI enforces 8 while declaring 10). **Neither rate limit binds at 50 calls** — hence W0 cut #8 removes `throttle_event`.

**The riskiest open assumption** (W0): whether `vapi.websocket` calls consume concurrency slots or **queue silently**. If they queue, (a) the 50-tile grid is a lie because tiles 11–50 sit in a vendor queue rendering as in-flight, and (b) every latency number is invalid because `concurrency_blocked` can only be set from a signal the harness never receives. ~15 min, ~$0.25 to test by extending `probe_vapi.py` to twelve simultaneous calls and comparing time-to-first-downlink-byte. **Do this before writing a line of `RunEngine`.**

## 3.7 Evaluation and scoring (W3 §9), with W0's defects

Transcript + timing only in v1 (audio-native deferred for *bias* reasons, not cost). Assertion types: `contains`/`not_contains`, `regex`, `latency_p95_under`, `turn_count_under`, `tool_called`/`tool_not_called`, `no_pii_leak`, `resumes_after_backchannel`, `llm_judge`. Every assertion is `blocking` or `advisory`; a call fails only on blocking; target ≥60% rule-based. "Rule-based" ≠ stable — normalize both sides with `EnglishTextNormalizer`, prefer fuzzy thresholds for phrase-shaped checks, reserve exact match for machine tokens, publish the flip rate over 3 identical runs.

Judge: binary pass/fail + written critique; **vendor identity blinded** (self-preference 0.73 → 0.32); model/version/temperature/seed in the run record; a judge swap invalidates comparison; verdict cache on disk (W1 notes the hit rate is **low** against a live agent — hence W0 cut #5). Calibration published at N=30 with raw agreement, Cohen's κ, false-pass/false-fail separately, class balance, Wilson CI, human–human ceiling.

**Two W0 defects:**
- **F5 no stored scores.** `assertion_result` has `blocking` but no weight, and there is no `run_score` table, so the grade is recomputed at render time and changing the scorer silently changes every historical grade. *Fix:* `run_score(run_id, scope_kind ∈ {run,category,tier}, scope_key, score, n_pass, n_fail, n_not_executed, scorer_version)`; refuse comparison across differing `scorer_version`.
- **F10 evidence offsets don't identify their transcript.** `turn_transcript` holds up to four rows per turn with different text and offsets, so the pinned timeline flag highlights the wrong span whenever sources differ. *Fix:* `evidence_source TEXT NOT NULL` FK to `(turn_id, source)`.

**F18 economics omission:** the harness line ("~$0.01/min · ~$1") ignores that 150 minutes of audio must pass through `whisper-pinned` — local means tens of minutes of wall clock *after* the run, delaying the card; hosted means uncosted dollars. ~8 assertions × 50 calls × multi-thousand-token transcripts is 1M+ judge input tokens, several times $1. **The wall-clock one is the schedule risk.**

## 3.8 Results and reporting (W3 §8.1, §10)

Four terminal states, exactly one always written: `shipped` / `partial` / `deadline` / `failed`, paired with `complete | budget_aborted | infra_aborted`. Unrun tests are `not_executed`, never 0. **Only `complete` may render a grade or an average.** Exit codes 0/1/2/3.

Eight headline metrics: survival rate · safety score · voice-to-voice latency p50/p95 · interruption handling · task completion · **cost per resolved call** · language robustness (+WER by locale) · hallucination rate. Plus all per-test scores, category averages, and survival by difficulty tier — **which F4 shows have no data source without a `test_case` table**.

Metrics nobody else produces: `transcriber_divergence_wer` (cut by W0 #7 — keep only `ground_truth` vs `pinned_whisper`, "the genuine differentiator and it's free") and the **STT diff against known truth**, computable because REPLAY synthesized the caller audio from text.

Card: local SVG→PNG; grade + `41/50` + tier breakdown; three worst failures in plain English; latency p95 with concurrency label; two cost lines; run hash + replication footer; and the mandatory framing line — *"This measures ONE DEPLOYED AGENT CONFIGURATION, not the vendor's platform."* Vendor named locally, stripped by default on publish. Plus `report.md` and `report.html`.

## 3.9 Entities — 26 tables, cut to 8–10 **[Δ6]**

**Runtime (W1 §8), 16:** `run`, `attestation`, `run_capability`, `call`, `turn`, `turn_transcript`, `assertion_result`, `judge_cache`, `dispute`, `tool_call`, `latency_metric`, `cost_ledger`, `audio_artifact`, `wire_event`, `throttle_event`, `pii_quarantine`, plus the `export_call` view. SQLite WAL, FK on, integer epoch-ms, `REAL` USD.

**Authoring (W2 §3.1), 10:** `agent`, `agent_config_version`, `agent_goal`, `test_category`, `test_case`, `test_case_goal`, `generation_job`, `suite`, `suite_version`, `suite_test`, plus two `ALTER TABLE run` columns (`suite_version_id`, `agent_ref_id`).

**W0's cut list, in order** (cut from the top until 35 hours fits): Retell adapter → LIVE mode/`pyai-omni` caller → `pii_quarantine` + detect-before-write (F9) → `dispute` + splits → `judge_cache` → `tool_call` → `transcriber_secondary` → `throttle_event` → `latency_metric` (collapse to `turn.t_response_ms`, `turn.t_stop_ms`, `call.vendor_latency_json`) → `cost_ledger` (four REAL columns on `run` + one post-run poll) → `run_capability` (JSON blob on `run`) → `export_call` view (F8) → `mode='observed'` → **MCP client surface**.

**Result: 16 → 8**, plus two new tables the review *adds*: `persona`/`test_case` (F4) and `run_score` (F5). Final runtime set: `run`, `test_case`, `call`, `turn`, `turn_transcript`, `assertion_result`, `audio_artifact`, `run_score`, plus `wire_event` and `attestation` ("both one-insert-cheap"). If S1 lands the authoring layer, add its 10 — but note `test_case`/`test_category` are then shared, so the real total is ~18.

**F9's argument for cutting the quarantine, since it is the largest single reclaim (~6–10 h of 35):** `start_offset`/`end_offset` don't say whether they index raw or redacted text and cannot be both (`[PII:PERSON_NAME]` is 18 chars, `Bob` is 3); `origin_ref INTEGER` is a polymorphic FK where `origin='transcript'` points at `turn_transcript`, whose PK is the composite `(turn_id, source)` — unreferenceable by an integer — and `origin='vendor_summary'` references a table that does not exist; `PERSON_NAME` needs NER (model download, thread pool, new failure mode). Replacement for the window: a regex pass at export time plus a banner — *"not PII-safe; do not point at production."*

## 3.10 APIs and services

**One local Python process** (W1 §2): asyncio, SQLite + files under `./data`, no Docker, no account. `wiretap serve` is the same process serving static assets and SSE — which **F17** notes is a server, and "no server" invites you not to plan for SSE's real failure modes (proxy buffering, connection caps, reconnect-on-sleep) at 50 tiles on conference wifi.

| Surface | Contract |
|---|---|
| **CLI** | `init`, `doctor`, `providers add`, `agents list`, `suites list`, `run`, `report`, `card`, `replay`, `compare`, `serve`, `contribute-label`, `purge-quarantine` — plus W2's `agents snapshot`, `agents goals`, `suite generate/show/versions/edit/regenerate/diff` |
| **HTTP (W2 §5.2)** | 12 routes under `/v1/…`, each a thin wrapper over one service; `POST …:generate` returns **202 + `generation_job` id**, progress over SSE |
| **MCP** | 6 tools — **cut from v1 by W0 #14** |
| **Adapter, required** | `connect`, `send_audio`, `recv`, `teardown` |
| **Adapter, declared** | `fetch_vendor_transcript`, `fetch_tool_calls`, `fetch_cost`, `list_agents`, `set_recording_suppression`, `agent_version_signal`, `fetch_latency_breakdown` (Vapi), `fetch_rag_trace` (Retell) — each returning an explicit `Unsupported` sentinel, "never zero, never an empty success" |
| **Services (W2 §5.1)** | `AgentImporter`, `ConfigSnapshotter`, `GoalExtractor`, `SuitePlanner`, `TestGenerator`, `TestValidator`, `SuiteAssembler`, `SuiteRegistry` — meeting the runtime at exactly one seam: `SuiteRegistry.resolve(suite_version_id) → RunEngine.run()` |

**Non-obvious adapter requirements** (W1 §9.1): Vapi HTTP needs a non-default User-Agent (Cloudflare returns a plain-text `403 error code: 1010` that reads like auth failure); `fetch_cost` must poll; PyAI credit doesn't move in real time; **the persona linter must read the target's stop words** or a persona saying goodbye ends the call and looks like an agent failure; per-agent latency config must be recorded or two agents aren't comparable.

## 3.11 UI requirements (W3 §12 + W2 §6)

Runtime screens: first-run blocking warning → HOME → PROVIDERS → AGENT PICKER → RUN CONFIG → PRE-FLIGHT → **LIVE GRID** (50 tiles, grouped by category, spend meter, Abort) → RESULTS → CALL DETAIL → COMPARE → CARD.
Authoring screens (W2 §6): Providers → Agents (name, vendor, external id, config version, last snapshot, suite count, **prompt-access badge**) → Agent detail (extracted goals for confirmation and editing, category target matrix, industry, business context, prompt-access choice **with its consequence stated inline**, estimated cost and duration) → Generate → **Suite list** (10 required columns incl. **config status green/amber** and a **publishable lock icon with a tooltip naming the reason**) → Suite detail (test table with origin badge, citation link, enabled toggle, last result; changes batch into a **pending diff** committed as one new version).

**Combined call timeline**: one dual-tinted waveform, not two stacked, so barge-in shows as literal overlap. v1 ships three layers — waveform, turn boundaries, assertion flags pinned to timestamps — frozen for the screenshot; latency bars, tool calls, guardrail hits and cost move to hover and a second tab. Single synced cursor, click a flag to seek, transcript scroll-locked, **STT diff inline as strikethrough/insert**. **F8** notes this view needs `turn`, `turn_transcript`, `assertion_result` and `wire_event` — which the `export_call` view cannot supply.

## 3.12 Architecture requirements (W1 §2, §4)

Canonical **PCM16 LE mono @16 kHz** inside the harness; 20 ms = 320 samples = 640 bytes. **Framing is asymmetric between vendors** — Vapi takes untagged raw PCM, PyAI requires a `0x01` tag and **silently drops untagged frames with no error, no log, no counter**; sharing frame-construction code between them produces a silent failure. PyAI downlink is 24 kHz regardless of input, so resampling is required. Pacing `next_send = max(next_send + 0.020, time.monotonic())`. Turn detection by RMS over 20 ms windows, onset above threshold, offset after 250 ms below. **No diarization, ever.** WAV: PyAI Speak writes `0xFFFFFFFF` into RIFF and `data` sizes — never trust the header (3.36 s reports 134,217 s), walk the chunks, compute from byte count.

**Determinism:** the **local SHA-256 WAV cache is the source, not the TTS engine** — verified ❌ that PyAI Speak is reproducible (two cache misses shared no 400-byte sequence at any offset); `seed`/`temperature` are accepted, inert, and not part of the vendor's cache key.

**Missing per W0, all infrastructure:** schema migrations (`PRAGMA user_version`, a runner, `db reset`) · **resume of a partial run** (`wiretap run --resume`, ~30 lines of demo insurance, because a crash at call 40/50 currently means money spent and no card) · **SIGKILL/orphaned vendor calls** (`wiretap reap` + a signal handler; WAL saves the DB, it does not hang up ten in-flight calls that keep billing and holding slots) · **error taxonomy** · **harness self-observability incl. a silent-drop guard** (`call.tx_bytes`, `call.rx_bytes`, `call.pacer_underruns`, and the invariant `tx_bytes > 0 AND rx_bytes > 0` or the call is `error`, never `failed`) · **backpressure** (nothing is bounded) · **disk growth** (~11.5 MB/call × 50 = **~600 MB/run**; ten dev runs is 6 GB) · **a determinism verification command** · **who writes the 50 personas** · **any testing strategy for the harness**.

## 3.13 Future (W3 §20, W2 §9, W0)

v1.1: BYO-Twilio + SIP (gated on a mandatory compliance section); Deepgram adapter (`InjectAgentMessage` with `behavior: interrupt` — the only documented deterministic barge-in primitive); Retell if cut now; the authoring layer if S1 defers it. v1.2: judge panel (3 disjoint families, better κ at 7–8× lower cost); audio-native scorers; `dispute` + golden set; `judge_cache`. v1.3: leaderboard (PR-submitted signed `result.json` verified by an Action); production monitoring as a source adapter. v2: prompt-aware generation at `prompt_access='stored'`.

---

# PART 4 — LangWatch → Wiretap mapping

**Adopt** (take the pattern) · **Adapt** (take the shape, change the mechanism) · **Inspired by** (principle only) · **Not required** · **Future**. Rows marked **[Δ1]** changed from draft 1.

| # | Wiretap requirement (source) | LangWatch concept | What we learn | How we adapt it | Verdict |
|---|---|---|---|---|---|
| 1 | `run/call/turn` hierarchy (W1 §8) | `thread_id`/`trace_id`/`span_id` | Three IDs model arbitrary depth; the *set* is the versioned unit | Keep; the "set" is `suite_version_id` | **Adapt** |
| 2 | Live grid + SSE (W3 §12.2) | `SCENARIO_RUN_STARTED`/`MESSAGE_SNAPSHOT`/`RUN_FINISHED` + 4 shared ids | A 3-event protocol suffices for a live simulation UI | `call_started`/`call_progress`/`call_finished` + `run_progress` | **Adopt** (shape) |
| 3 | Error taxonomy (**W0 missing**) | `status ∈ SUCCESS\|FAILED\|ERROR`; error-group inspection | A closed status enum is what lets a UI colour-code and triage | `call.error_kind` enum on `call_finished`; grid colours from it | **Adapt [Δ1]** |
| 4 | `assertion_result` (W1 §8.3) + **F5** | `add_evaluation(name, score, passed, label, details)` | One contract serves booleans, scores and categories | Add `score REAL NULL`, `label TEXT NULL`; keep `blocking`, add `evidence_source` (F10) | **Adapt** |
| 5 | Stored grades, `scorer_version` (**F5**) | Projections are **materialized and versioned**, rebuilt by explicit replay | Derived data must be written down and stamped, not recomputed at read | `run_score` table; renderer pure over it; `rebuild` writes new rows, never overwrites another `scorer_version` | **Adapt [Δ1]** |
| 6 | Assertion type registry (W3 §9.2) | Evaluators addressed by namespaced slug | Slugs let new families land without a schema change | `rule/contains`, `judge/boolean`, later `audio/frustration` | **Adapt** |
| 7 | Suite = immutable version (W2 C3) | `Experiment` → `ExperimentRun`; prompt entity → immutable version snapshots (`version`, `versionId`, `authorId`, `deletedAt`) | Definition/execution split; identity in the parent, immutability in the version; soft delete | Validates `suite`/`suite_version`; **add an author field to version rows** | **Adopt [Δ1]** |
| 8 | Test generation (W2 §4) | **AI dataset generation**: generate → validate → **human review before finalize**; generated records marked for provenance | A human gate belongs *before* records are finalized | Insert **staging → review → finalize** between W2 stages 4 and 5 | **Adapt [Δ1]** |
| 9 | `generation_job` (W2 §3.1) | Experiments: run → **poll** → read results; `status` enum | Long work = job id + poll/stream + a `partial` terminal state | Already W2's shape (202 + SSE); keep `partial` | **Adopt [Δ1]** |
| 10 | `test_case` + `test_category` (**F4**, W2) | Datasets: typed columns, records, versioning, staging, provenance | Test cases must be rows, not files, once they are generated per-agent | Seed the standard corpus into `test_case` rows (answers S2); categories as rows | **Adapt [Δ1]** |
| 11 | `agent` + `agent_config_version` (W2 §3.1) | `agents` CRUD API; model-provider entities | Agents are entities; configs are immutable snapshots | Keep W2's tables; `prompt_sha256` always recorded | **Adopt [Δ1]** |
| 12 | Terminal states + no-grade rule (W3 §8.1) | Projections + run status | If the card is pure over *stored* scores, the rule is structural | Renderer takes `(run_score rows, run_status)` and nothing else | **Adapt** |
| 13 | Crash/SIGINT invariant (W3 §8.4) | Immutable events + rebuildable projections | Durable append + derived read makes crash-safety a property | Append-only tables; derived tables recomputed by `rebuild` | **Adapt** |
| 14 | `report`/`card`/`verify` (W3 §11, **F1**) | **Projection Replay** with dry-run | Re-derivation is a first-class verb | `wiretap rebuild <run> [--dry-run]`; `wiretap verify <a> <b>` for the hash claim | **Adapt** |
| 15 | "Replayable exactly" (W3 §5.3) | **Deja View** | Event history + reconstruction generalizes replay | `wire_event` is the history; `replay <call>` reads it | **Adapt** |
| 16 | Testing the harness (**W0 missing**) | **The Foundry** | A mature system needed a synthetic-input playground | **Loopback/fixture transport, hour 1** | **Adopt** |
| 17 | `wire_event` payload bloat (**F12**) | Externalized object content to S3; PII redaction stage | Large repeated payloads must be content-addressed, not inlined | `payload_blob(sha256 PK, text)` + `wire_event.payload_sha256`; denylist the customer's system prompt | **Adapt [Δ1]** |
| 18 | Backpressure (**W0 missing**) | Bounded queue + DLQ + drain | Unbounded queues are the real failure mode | Bounded writer queue; drop `wire_event` first under pressure; **no DLQ** | **Adapt [Δ1]** |
| 19 | PII handling (W3 §15.3 vs **F9**) | PII redaction *before* storage | The boundary is right even when the implementation is too expensive | Keep the *principle*; for the window use F9's regex-at-export + banner | **Inspired by [Δ1]** |
| 20 | Publish surface (**F8**) | Narrow, auth-scoped read surfaces | The publish path needs its own narrow surface | **One serializer module + a frozen-keyset test.** Not a SQL view | **Inspired by [Δ1]** |
| 21 | Cost (W3 §14, **F11**) | `CostEnriched` stage; derived server-side | A corrected price table should be retroactive | `run.pricing_yaml_sha256`; `amount_usd` nullable with `basis='unsettled'`; `run.cost_settled` | **Adapt [Δ1]** |
| 22 | Budget caps (W3 §8.7, **F11**) | Soft-warn vs hard-block | Naming the two behaviors distinctly is clearer | Label the $5 confirm `soft`, the caps `hard`; **state plainly that enforcement is an estimate** | **Inspired by** |
| 23 | Latency (W3 §10.3, **F14**) | TTFT; `result.latency` TTFB/p50/p95 | They have no validity flag — but we have an unrecorded +250 ms bias | Keep validity + concurrency labels; **add `rms_threshold`, `hangover_ms` to `run`** | **Not required** |
| 24 | Clock reconciliation (**F2**) | One epoch per span, one axis | Three clock bases cannot share a timeline | `t_rel_ms` from `call.started_at`; `call.t0_monotonic_ns` as the anchor | **Not required** |
| 25 | Dispute → golden set (W3 §9.6, cut #4) | Datasets from traces; typed annotation score fields | Typed single-select labels are computable; free text is not | v1.2. Then: single-select label + separate reasoning + a documented `unclear` rule | **Future [Δ1]** |
| 26 | Annotation queues/members | Queues, assigned members, admin settings | Multi-annotator workflow | Single-user local tool | **Not required** |
| 27 | `mode='observed'` (W3 §16.3, **F3**) | Two endpoints, one pipeline | Different provenance, one write path | v1.3 as a source adapter with `run_source`, not a nullable FK | **Future [Δ5]** |
| 28 | Capability registry (W3 §7.3, cut #11) | Config-as-data | Config over code branches | Keep the registry; snapshot as a JSON blob on `run`, not a table | **Inspired by** |
| 29 | `Unsupported` sentinel (W1 §9) | — | Nothing to borrow; Wiretap is ahead | Keep — it is what makes the budget governor safe | **Not required** |
| 30 | Three front doors (W3 §4.1, gate 12) | Same image, different entrypoint | One artifact, many roles, enforced by packaging | CLI + UI over one SDK; import-boundary lint; **MCP cut** | **Inspired by** |
| 31 | Single-writer store (W3 §8.6) | BullMQ producer/consumer | Decoupling producers from a serialized consumer | Bounded `asyncio.Queue`, one consumer | **Adapt** |
| 32 | Async scoring (W1 §6) | Evaluation as a pipeline stage | Scoring async to capture keeps the hot path clean | Already the design | **Adopt** |
| 33 | Migrations (**W0 missing**) | Versioned upgrade paths, documented v3 migration | Schema evolution needs a runner and a version stamp | `PRAGMA user_version` + numbered migrations + `db reset` | **Adapt [Δ1]** |
| 34 | Storage (W1 §8) | ClickHouse/PG/Redis/S3, tiered | Split planes at scale | SQLite WAL + files | **Not required** |
| 35 | Analytics/dashboards/graphs | Dashboards, Graphs, timeseries | Configurable aggregation contradicts F5 *and* the no-grade rule | Fixed card, fixed 8 metrics | **Not required** |
| 36 | Monitors/triggers/guardrails | CRUD monitors, Slack, inline guardrails | Needs continuous traffic / request-path position | — | **Future / Not required** |
| 37 | Prompt management + DSPy | Full prompt product | W2 C1 governs prompt *access*, not prompt *authoring* | — | **Not required** |
| 38 | AI Gateway / virtual keys | Proxy, budgets, fallback, caching | Wiretap is a client | Only the soft/hard vocabulary | **Not required** |
| 39 | Orgs/teams/roles/SCIM/SSO/`ee/` | Full RBAC + licence gate | One user, one machine, MIT | — | **Not required** |
| 40 | Suite management UI (W2 §6) | **Suites API**: list/get/update/**duplicate**/**trigger run**/archive | Their nouns and verbs are nearly W2's routes, duplicate included | Adopt the verb set; keep it local and unauthenticated | **Adapt [Δ1]** |
| 41 | Typed event kinds | Span types with rendering consequences | Typed enums beat free-text `kind` | Constrain `wire_event.kind` to an enum + `other` | **Adapt** |
| 42 | Competitive positioning (W3 §1) | **Scenario does voice first-class** | The "no OSS duplex audio" wedge is false | Reposition per §7.3 | **Adopt** (the correction) |

---

# PART 5 — Wiretap architecture, informed by the above

**A** = required by a Wiretap doc · **B** = inspired by LangWatch · **C** = my proposal, needs a yes/no.

## 5.1 Agent representation — **A** (reversed from draft 1) **[Δ7]**

`agent` (`UNIQUE (vendor, external_id)`, `prompt_access`, `archived`) + `agent_config_version` (immutable, `config_sha256`, `prompt_sha256` always, parsed fields incl. `end_call_phrases`, `tools_json` with `irreversible`, `latency_config_json`). **A: W2 §3.1.** Even if S1 defers generation, these two tables are the only home for W1 §9.1's stop-word linter and latency-config comparability requirements.
**B (from prompt versioning):** add `authored_by`/`created_by` to version rows and prefer soft delete (`archived`) over `DELETE` — LangWatch's version snapshots carry `authorId` and `deletedAt` for exactly the "who changed this and when" question a regenerated suite raises.

## 5.2 Agent configuration and prompt policy — **A** + **B**

**A:** W2 C1's `prompt_access ∈ none|transient|stored`, with `prompt_sha256` always recorded so drift is detectable without storing text.
**A (F12), and this is the part C1 alone does not cover:** Vapi ships the full system prompt on **every** `conversation-update` frame, so the prompt enters `wire_event` payloads regardless of policy. The §8.8 denylist must cover the customer's system prompt, and §5.4's payload dedup is what makes that enforceable rather than aspirational.
**C:** state the `prompt_access` consequence *at the point of choice* in the UI (W2 §6 already does) **and** in `wiretap doctor` output, because CLI users never see that screen.

## 5.3 Scores, projections, and the card — **A** (F5) reconciled with **B** **[Δ2]**

Draft 1 said "card as a pure projection recomputed at render." F5 shows why that is a defect. The reconciliation keeps both properties:

```
append-only (never rewritten):  wire_event, turn, turn_transcript, audio_artifact, attestation, run(config cols)
materialized once, versioned:   assertion_result → run_score(scope_kind, scope_key, score, n_*, scorer_version)
pure render over materialized:  card.png · report.md · report.html
```

**Rules:**
1. Scores are written **at scoring time** with `scorer_version`. **A: F5.**
2. The card renderer's only inputs are `run_score` rows plus `run_status`. It has no code path from raw assertions to a letter grade. **A: W3 §8.1** — this is what makes gate 4 structural.
3. `wiretap rebuild <run> [--dry-run]` re-derives report artifacts and, if the scorer changed, **writes new `run_score` rows under the new `scorer_version`** rather than overwriting. **B: Projection Replay, including their dry-run.**
4. `wiretap compare` refuses across differing `scorer_version`, `suite_version_id`, or agent tuple, and **names which one differs** (W2 E7).

**Explicitly not adopted:** an event-sourcing framework, aggregate abstractions, or an event bus for storage. The "log" is ordinary tables with an ordering column.

## 5.4 Event modelling, SSE, and payload cost — **A** need, **B** shape

**A:** the live grid needs per-call state in real time; `serve` streams SSE (W1 §2, F17).
**B:** adopt LangWatch's three-event shape rather than inventing one, extended with the error taxonomy W0 lists as missing:

```
event: call_started    { run_id, suite_version_id, test_case_id, call_id, seq, category, tier, t }
event: call_progress   { call_id, turn_seq, role, t_rel_start_ms, t_rel_end_ms, partial_text?, t }
event: call_finished   { call_id, status ∈ passed|failed|skipped|not_executed|error,
                         error_kind ∈ connect_refused|auth_403|concurrency_reject|ws_abnormal_close|
                                      no_audio_rx|beat_timeout|transcribe_failed|judge_failed|null,
                         results:[{assertion_id, verdict, blocking, reasoning?}],
                         tx_bytes, rx_bytes, pacer_underruns, latency_valid, t }
event: run_progress    { executed, total, spend_usd_estimated, terminal_state?, run_status?, t }
event: generation_progress { job_id, produced, requested, rejected_counts, status, t }
```

**A (W0):** `error_kind`, `tx_bytes`, `rx_bytes`, `pacer_underruns` are all named as missing; putting them on the finish event is what lets the grid colour-code and makes the silent-drop invariant (`tx_bytes > 0 AND rx_bytes > 0` or `error`) visible instead of inferred.
**C:** `run_progress` and `generation_progress` are mine — LangWatch polls batch summaries; Wiretap's spend meter and 202-generation both need push.
**B/A (F12):** constrain `wire_event.kind` to an enum, and store payloads content-addressed:

```sql
CREATE TABLE payload_blob (sha256 TEXT PRIMARY KEY, text TEXT NOT NULL, first_seen INTEGER NOT NULL);
-- wire_event.payload_sha256 REFERENCES payload_blob(sha256)
```
This turns F12's ~14 MB of duplicated system prompt into one row, and it is the same move LangWatch makes by externalizing large object content rather than inlining it.
**A (F17):** plan for SSE's failure modes — heartbeat comment every 15 s, `Last-Event-ID` resume, and a polling fallback for `run_progress`. "No server" in W1 §2 should be restated as "no daemon, no account, loopback-only."

## 5.5 Execution, async model, backpressure — **A**, principle from **B**

**A:** two coupled tasks per call in one `asyncio.TaskGroup` (F13), `ping_interval=5`/`ping_timeout=10`, a hard deadline task, semaphore released in `finally`, terminal status written by the group owner. Append-only event sequence with a TX cursor + per-beat `timeout_ms` (F6). `beat.after ∈ {agent_speech_start, agent_speech_end, caller_beat_end}` + `after_ms` (F7). Buffer PCM to ~1 s chunks; bound the writer queue; drop `wire_event` first under pressure (F12).
**B (principle only):** "evaluation is a pipeline stage, not a request handler" — already satisfied by scoring after teardown. **Reject** the mechanism (worker pods, Redis).
**A/B:** the single writer is a **bounded** `asyncio.Queue` with exactly one consumer — BullMQ's producer/consumer decoupling at 1/1000th the cost, with the boundedness W0 says is missing everywhere.

## 5.6 PII and the publish surface — **A**, with two draft-1 withdrawals **[Δ3]**

**A (F9, for the window):** cut `pii_quarantine` and detect-before-write; ship a regex pass at export time plus the banner *"not PII-safe; do not point at production."* Recovers ~6–10 h of 35. The W3 §15.3 boundary rule remains the right long-run design and returns when NER does.
**A (F8):** drop `export_call`. The publish path gets **one serializer module** whose output keyset is asserted equal to a frozen literal in a test (~20 min). Draft 1's proposal to add more views is withdrawn — the view mechanism cannot express the timeline's five-table join and gives no compile-time guarantee.
**A (F12 + W2 C1):** extend the redaction denylist to the customer's system prompt, alongside `transport.websocketCallUrl` (✅ verified unauthenticated — the URL alone joins a live call), `monitor.listenUrl`/`controlUrl`, `presigned*Url`, PyAI `resume_token` (30 s session takeover), and any key/Bearer/LiveKit token.
**B (principle):** the risky path gets its own narrow surface. Mechanism is ours.

## 5.7 Evaluation modelling — **A** core, **B** contract

**A:** assertion types, `blocking`/`advisory`, ≥60% rule-based, normalization before matching, judge blinded, verdict cache keyed on `sha256(criterion‖messages‖model‖temp)` (W0 cut #5 defers the cache itself; keep `judge_cache_hit` defaulted 0).
**B + A(F5, F10):** align `assertion_result` with LangWatch's universal contract and close two defects in the same migration:

| LangWatch | Wiretap | Action |
|---|---|---|
| `name` | `assertion_id` | exists |
| `passed` | `verdict ∈ pass\|fail\|skipped\|error` | exists — richer, keep |
| `score` | — | **add `score REAL NULL`** (F5 needs a numeric channel) |
| `label` | — | **add `label TEXT NULL`** |
| `details` | `judge_critique` | exists |
| — | `evidence_source` | **add** — FK to `(turn_id, source)` (F10) |
| — | `blocking`, `rule_based`, `evidence_*` | Wiretap-only, keep |

**`blocking` has no LangWatch equivalent and is Wiretap's most important scoring idea — the alignment must not erode it.**
**C:** namespaced evaluator slugs (`rule/…`, `judge/…`, later `audio/…`) so new families land as data.

## 5.8 Test-case and suite modelling — **A**, reversed from draft 1 **[Δ4]**

**A (F4 + W2 §3.1):** `test_case` and `test_category` are tables. `category_id` and `difficulty_tier` are denormalized onto `call` so old runs stay roll-up-able after a corpus edit. `fingerprint` = sha256 over normalized beats + sorted assertions, with `UNIQUE (suite_version_id, fingerprint)`.

**C — recommendation for S2:** **seed the standard corpus into `test_case` rows at first run** with `origin='standard'`, keeping the YAML pack as the *shipping format* and the table as the *runtime source*. Rationale: it gives `core-50@v1` and generated suites one code path (the thing S2 asks about), it satisfies F4 without a second lookup path, and it costs one seeder plus a `fingerprint` check for idempotency. The YAML stays authoritative for PRs and diffs, so Sam-the-contributor's workflow is unchanged.

**B (from AI dataset generation + the datasets staging API) — insert a review gate:**

```
stage 4 VALIDATE → stage 4.5 STAGE  → human review (accept / edit / drop / regenerate cell)
                                    → stage 5 FINALIZE → suite_version v1
```
LangWatch's generator validates and then requires **human review before records are finalized**, backed by `update-staging` / `action-finalize` / `action-retry`. W2 today assembles v1 directly, which means a generated suite becomes an immutable version before anyone has read it, and E5's "manual edits create a new version" then makes the first review pass produce v2 immediately. Staging removes a spurious version and gives C2's `publishable=0` a human decision point rather than a silent flag. **~2–3 h; recommend it only if S1 lands generation in the window.**

**A (W2 E2):** regeneration carries manually added tests forward by default.

## 5.9 Cost — **A** (F11) + **B**

**A (F11):** `amount_usd` nullable with `basis='unsettled'`; add `run.cost_settled`; the card must not render a total while unsettled rows exist; state plainly that BudgetGovernor enforcement is an **estimate** and W1 §6.2's overshoot formula is the only guarantee. If W0 cut #10 collapses the ledger to four columns on `run`, the same three properties must survive as `cost_agent_usd`, `cost_harness_usd`, `cost_basis`, `cost_settled`.
**B:** add `run.pricing_yaml_sha256` so `rebuild` can re-derive `derived` rows under a corrected price table while leaving `reported` rows untouched, and the card can name the pricing snapshot it used. One column; LangWatch's cost-as-pipeline-stage is the precedent.
**A (F18):** budget the **transcription wall clock** and the judge's real token cost in the schedule, not just in dollars.

## 5.10 Ingestion and future observed mode — **Future** **[Δ5]**

Cut `mode='observed'` now (F3, cut #13); make `persona_id`/`test_case_id` NOT NULL; use `UNIQUE (run_id, seq)` + `repeat_index INTEGER NOT NULL DEFAULT 0` so **running the same test N times for score stability is expressible** — which W1 §5's measured-stability claim requires and the current constraint forbids. When production ingest lands in v1.3, add `run.run_source` and a source adapter emitting the same `turn`/`wire_event` rows — LangWatch's "two provenances, one pipeline" holds, just not through a nullable FK.

## 5.11 Versioning — **A**, three axes

**A (W2 E7):** `agent_config_version.config_sha256` + `vendor_version` (drift check), `suite_version.version` + `content_sha256`, `run_score.scorer_version`. `compare` refuses unless all three match and names the differing one. Plus `harness_git_sha` on every run, and `run.caller_audio_set_sha256` (F1) — without which the headline claim is not queryable.
**A (F1):** `wiretap verify <run_a> <run_b>` compares caller-audio set hashes and reports identical/differing. This command does not exist and the demo depends on it.
**B:** immutable version + movable tag for *user* packs only; never resolvable in a published artifact.

## 5.12 APIs — **A** (W2 §5.2), boundary discipline from **B**

W2 already specifies 12 `/v1/…` routes with CLI parity, each a thin wrapper over one service, and `POST …:generate` returning 202 + job id with SSE progress. Draft 1's invented `/api/…` shape is **withdrawn** in favour of W2's. Two additions:
**C:** `GET /v1/runs/{id}/events` (SSE, the §5.4 events) and `POST /v1/preflight` (config in, gate results out, no side effects) — the pre-flight screen needs the second and no route covers it.
**B:** enforce the layering with an import-boundary lint (W3 §17.2), because gate 12 is the constraint most likely to erode under time pressure — and note W0 cut #14 removes MCP, so gate 12 is now CLI + UI only.

## 5.13 Storage and disk — **A** + **C**

SQLite WAL + files, no Docker. **A (W0):** `PRAGMA user_version` + numbered migrations + `db reset`, before two engineers share `./data/wiretap.db`. **A (W0):** ~600 MB/run is uncosted; add `wiretap prune --keep-last N` and document the footprint. **C:** store PCM as FLAC or gzip after scoring (roughly 2–3× on speech) — cheap, and the audio is only needed for replay after that point.

## 5.14 The loopback/fixture transport — **A**, hour 1 **[upgraded]**

Three independent passes converged: W0's "Missing entirely" opens with it, README records the convergence, and LangWatch's Foundry is the mature-product precedent. Scope:

- A `local-demo`/`fixture` adapter satisfying the required-core contract by replaying a canned `(wire_event, PCM)` stream at 20 ms pacing, with knobs for: agent-only vs mixed downlink, tagged vs untagged framing, mid-call socket drop with **no FIN** (half-open, F13), 429 pre-upgrade, silent queueing, a `0xFFFFFFFF` WAV, and a `conversation-update` frame carrying a 9 KB prompt (F12).
- Fixtures checked in — synthetic, so no PII or licensing question; W1 already has `out/agent_leg.wav` + `text_frames.json` on disk from the probes.
- It is also the demo target: no vendor ceiling, no ToS exposure, $0, and the only honest way to show 50 concurrent tiles while Vapi allows 10.
- Every acceptance gate not needing a live vendor runs against it in CI: **gates 2, 3, 4, 6, 8, 9, 10, 11, 12**.

## 5.15 Ops verbs — **B** shape, **A** need

| Verb | Status | Analogue / source |
|---|---|---|
| `wiretap doctor` | **A** (W3 §11.1) | health check |
| `wiretap verify <a> <b>` | **A** (F1) | — the headline claim |
| `wiretap rebuild <run> [--dry-run]` | **C** (§5.3) | Projection Replay |
| `wiretap replay <call>` | **A** (W3 §11.1) | Deja View |
| `wiretap run --resume <run_id>` | **A** (W0 missing) | ~30 lines of demo insurance |
| `wiretap reap <run_id>` | **A** (W0 missing) | orphaned in-flight calls keep billing |
| `wiretap prune --keep-last N` | **A** (W0 missing) | retention |
| `wiretap db migrate / reset` | **A** (W0 missing) | migration runner |
| `wiretap purge-quarantine` | deferred with F9 | — |

**Reject:** DLQ, queue draining, error-group inspection. Bounded retry then `not_executed` is simpler and correct for a bounded local run.

## 5.16 Future evaluator support — **A** shape, **B** interface

The §5.7 contract (`verdict` + nullable `score`/`label` + namespaced slugs) already accommodates the v1.2 judge panel and audio-native scorers. The panel needs one child table (`judge_vote`) **in v1.2**; W3 §9.4 already fixes majority semantics.

---

# PART 6 — Over-engineering filter

| LangWatch capability | Need it? | In a Wiretap doc? | Solves a Wiretap problem? | Simplify to | Now / later / never |
|---|---|---|---|---|---|
| ClickHouse / Postgres / Redis / S3 tiering | No | No — SQLite mandated | No | One SQLite file + files | **Never** |
| Worker pods, NLP + LangEvals services | No | No — one process | Partly (evaluator isolation) | In-process modules behind one interface | **Never** as services |
| Event-sourcing framework | No | No | The *principle* does (F5, crash invariant) | Append-only tables + materialized `run_score` + `rebuild` | **Now**, cheap form |
| Projection replay console | No | No | Yes | `rebuild --dry-run` | **Now** |
| Deja View | No | Partly (`replay`) | Yes | Read `wire_event` | **Now** |
| **The Foundry** | No (as a UI) | **Yes** (W0 missing) | Yes — 9 of 14 gates | Loopback/fixture adapter | **Now, hour 1** |
| Queue mgmt / DLQ | No | No | No | Bounded retry → `not_executed` | **Never** |
| Bounded queues + error groups | Yes | **Yes** (W0 missing) | Yes | Bounded writer queue + `error_kind` enum | **Now** |
| OTel as the internal model | No | No | No | Own `wire_event`/`turn` | **Never** internally |
| Datasets as entities | **Yes** | **Yes** (F4, W2) | Yes — rollups + generated cases | `test_case` + `test_category` rows, seeded from YAML | **Now [Δ4]** |
| Dataset staging → finalize | Maybe | No — W2 goes straight to assemble | Yes, if generation ships | One staging table + a review screen | **Now if S1 yes** |
| AI dataset generation | **Yes** | **Yes** (W2 §4) | Yes | W2's 5 stages; generator instantiates cited techniques only | **S1 decides [Δ1]** |
| Agents as entities | **Yes** | **Yes** (W2 §3.1) | Yes — linter + latency comparability | `agent` + `agent_config_version` | **Now [Δ7]** |
| Experiment/run split | **Yes** | **Yes** (W2 C3) | Yes — immutable suite versions | `suite` → `suite_version` → `run` | **Now [Δ1]** |
| Job + poll/SSE for long work | Yes | **Yes** (W2 §5.2) | Yes | `generation_job` + 202 + SSE | **Now if S1 yes** |
| Prompt management / DSPy | No | No | No | — | **Never** |
| Gateway / virtual keys | No | No | No | Keyring + 4 flat caps | **Never** |
| Dashboards / graphs / timeseries | No | No | No — contradicts F5 *and* the no-grade rule | Fixed card + 8 metrics | **Never** |
| Topic clustering | No | No | No | Authored categories | **Never** |
| Monitors / triggers / alerts | No | No (v1.3) | Not yet | — | **Later** |
| Guardrails in-path | No | No | No | — | **Never** |
| Annotation queues | No | No | No | `dispute` is cut anyway (#4) | **Never** |
| PII redaction as a stage | Principle yes | Yes (W3 §15.3) vs **F9** cut | Boundary is right, cost is wrong for the window | Regex at export + banner | **Principle now, impl later** |
| Content-addressed large payloads | **Yes** | Implied by **F12** | Yes — 14 MB/run | `payload_blob` + `payload_sha256` | **Now [Δ1]** |
| Versioned migrations | **Yes** | **Yes** (W0 missing) | Yes | `PRAGMA user_version` + runner | **Now [Δ1]** |
| Orgs/teams/RBAC/SSO/SCIM/`ee/` | No | No | No | — | **Never** |
| Governance ingestion / observed mode | No | v1.3 | Not yet | `run_source` later | **Later [Δ5]** |
| MCP server | Was yes | W3 §13, **cut by W0 #14** | Demo nicety | — | **Later** |
| Agent Skills packaging | No | No | Distribution | `SKILL.md` | **Later** |
| Evaluation result contract | Yes | Yes via **F5/F10** | Yes | 3 columns | **Now** |
| Three-event protocol + status enum | Yes | Yes (grid; W0 taxonomy) | Yes | 5 SSE events + `error_kind` | **Now** |

**Net new work this document proposes for v1** (beyond applying W0's own fixes): 3 columns on `assertion_result`, 1 column on `run` (`pricing_yaml_sha256`), a `payload_blob` table, a `wire_event.kind` enum, 5 named SSE events with an error enum, a corpus seeder, `rebuild`/`verify`/`prune`/`db migrate` verbs, the loopback transport with fixtures, an import-boundary lint, and — only if S1 says yes — a staging step before suite finalization. Everything else is either already in W0/W1/W2 or explicitly rejected.

---

# PART 7 — Final recommendation

## 7.1 What Wiretap should borrow, re-ranked for the 35-hour reality

Ordering changed from draft 1 because W0's cut list and defect fixes now compete for the same hours. Anything below the line is post-window.

| # | Borrow | Effort | Serves |
|---|---|---|---|
| 1 | **Loopback/fixture transport** (Foundry) | 4–6 h | 9 of 14 gates; the only way gate 12 is checkable; the honest 50-tile demo; makes every later cut safe |
| 2 | **Materialized `run_score` + `scorer_version`; renderer pure over it** (versioned projections) | 2–3 h | **F5**; makes the no-grade rule structural; makes `compare` trustworthy |
| 3 | **Three-event SSE + `error_kind` taxonomy + byte counters** | 2–3 h | Live grid; W0's missing error taxonomy and silent-drop guard |
| 4 | **`payload_blob` content addressing + `wire_event.kind` enum** | 1 h | **F12** — 14 MB/run of duplicated prompt; also the prompt-leak surface C1 doesn't cover |
| 5 | **Evaluation result contract** (`score`, `label`, `evidence_source`) | 45 min | **F5**, **F10**, and v1.2 forward-compat with no migration |
| 6 | **`test_case`/`test_category` rows seeded from the YAML pack** | 2 h | **F4** rollups; answers **S2**; one code path for standard and generated suites |
| 7 | **Versioned migrations** (`PRAGMA user_version` + runner + `db reset`) | 1–2 h | Two engineers on one `./data/wiretap.db` |
| 8 | **`run.pricing_yaml_sha256`** + F11's nullable/unsettled cost | 45 min | Retroactive price corrections; the card not lying while `settled=0` |
| 9 | **Bounded writer queue, drop `wire_event` first** | 1 h | W0's backpressure gap; F12's real failure mode |
| 10 | **`verify` / `rebuild --dry-run` / `resume` / `reap` / `prune`** | 2–3 h | **F1** headline claim; W0's four missing verbs |
| — | *line: below here is post-window* | | |
| 11 | Staging → review → finalize for generated suites | 2–3 h | W2 §4's missing human gate — only if S1 lands generation |
| 12 | Author field + soft delete on version rows | 30 min | "Who regenerated this?" |
| 13 | `SKILL.md` distribution; MCP surface | — | Cut by W0 #14; revisit v1.1 |

**Engineering practices worth copying wholesale:** publish your own sizing numbers (they document 2.6 CPU / 6.7 GiB; Wiretap should document 600 MB/run and the transcription wall clock); make operational actions first-class verbs, not DB surgery; put a dry-run on anything that rewrites derived data; keep the publish surface narrower than the internal one; ship a machine-readable index of your own artifacts (their `llms.txt` → Wiretap's parseable `report.md` + replication bundle, which is what a v1.3 leaderboard Action would verify).

**Data-modelling principles:** typed enums wherever rendering depends on the value; never overwrite a measurement; **write down derived values with the version of the code that derived them**; derive money from stored raw facts; identity in a parent row, immutability in version rows, soft delete over hard delete.

## 7.2 What Wiretap should not copy

**Outside our docs:** prompt management, DSPy, the gateway, dashboards/graphs/timeseries, topic clustering, monitors/triggers, guardrails, annotation queues, coding-agent governance, orgs/teams/RBAC/SSO/SCIM/audit, licensing tiers, governance ingestion.
**Unnecessary complexity here:** ClickHouse, Postgres, Redis/BullMQ, separate worker/NLP/evaluator services, tiered S3, dead-letter queues, an event-sourcing framework, OTel as the internal model.
**Product decisions that would actively hurt Wiretap:** hosted-first (local-only is the trust claim); configurable analytics (a hole in both the no-grade rule and F5's versioned scoring); mutable evaluator configs (a year-old run must still mean something — hence `run_capability` snapshots and three version axes); latency without a validity flag (though F14 means Wiretap must first record its own +250 ms hangover bias and 20 ms quantization before claiming the high ground).

## 7.3 What Wiretap must build itself — positioning, corrected

`langwatch/scenario` does voice first-class (ElevenLabs, OpenAI Realtime, Twilio Media Streams, Pipecat, Gemini Live; `scenario.interrupt()`; `scenario.audio()`; `background_noise()`; `result.latency`). **W3 §1's wedge — "no open-source tool drives real duplex audio" — is false and must be rewritten.** What remains defensibly Wiretap's:

| # | Uniquely Wiretap | Why they don't have it |
|---|---|---|
| 1 | **Deployed-agent adapters** for Vapi (and PyAI, and Retell if it survives) + a loopback demo agent | Their adapters target model-level realtime APIs and ElevenLabs; the deployed-agent platforms are exactly the ones with version pins, cost APIs and ToS constraints |
| 2 | **Byte-identical REPLAY determinism** from a local SHA-256 cache, with W1 §5's honest scope — *plus* F1's `caller_audio_set_sha256` and a `verify` verb, without which the claim isn't queryable | Their repeatability is "frames as data in CI", not a hash-verified set |
| 3 | **Ground-truth STT diff** (`turn_transcript.source='ground_truth'`) — scoring the agent's *hearing* separately from its *thinking* | Requires generating the caller audio, transcribing independently, and publishing the divergence |
| 4 | **Cost honesty**: two lines, cost per *resolved* call, `reported` vs `derived` vs `unsettled`, and `pricing.yaml` with mandatory `verified_on` + source | No dated pricing provenance exists anywhere in LangWatch; nobody in the category reports the test's own cost |
| 5 | **Safety as blocking gates**: ownership attestation, enumeration-as-proof-of-control, sandbox-key restriction, ToS posture registry, side-effect blocking + mock webhook server, two-tier findings with 90-day disclosure, and W2 C2's *instantiate-a-cited-technique-never-invent* generator constraint | These exist because Wiretap fires adversarial traffic at third-party production systems. LangWatch observes systems you already own |
| 6 | **Terminal-state grading discipline** — four states, `not_executed` never 0, no grade on a non-complete run, enforced by a renderer with no other code path | Their statuses feed dashboards; nothing structurally prevents a partial average |
| 7 | **Published judge calibration** — N, raw agreement, Cohen's κ, false-pass/false-fail separately, class balance, Wilson CI, human–human ceiling | No competitor publishes judge accuracy |
| 8 | **Concurrency-honest latency** — `latency_valid`, `measured_at_concurrency`, harness *and* vendor rows, once F2/F14 are applied | Their latency has no contamination flag |
| 9 | **Capability + ToS registry** driving auto-skip, clamping, which gates fire, and whether an adapter ships enabled — snapshotted per run | Nothing equivalent |
| 10 | **The authoring layer**: config-derived goals, a deterministic composition matrix, and generated tests that stay inside a cited technique with `publishable=0` when they don't | Their generator is an evaluation-dataset bootstrapper with no legal posture to defend |
| 11 | **Three version axes with loud refusal** (agent config / suite / scorer) | They version prompts and datasets; nothing refuses a comparison |
| 12 | **Combined dual-tinted waveform** with assertion flags pinned to timestamps and inline STT diff | Their visualizations are trace waterfalls and topology maps |
| 13 | **Local-only, no account, five-minute zero-key first run** | Structurally opposite to a hosted platform |

**Components to build (all Wiretap-only):** `RunEngine`, `SuiteLoader`/`SuiteRegistry`, `PersonaResolver`, `CallerDriver`, `AdapterRegistry`, `RateGovernor`, `BudgetGovernor`, `Transcribers`, `JudgeRunner` (blinded), `Scorer` + `run_score`, `ArtifactStore` (single bounded writer), card renderer, the 8–10 runtime tables (+10 authoring if S1), the 4+8 adapter contract, the CLI, the 12 `/v1` routes + SSE, the loopback transport, the persona/stop-word linter, the mock webhook server, `pricing.yaml`, and the demo agent — which is on the critical path as a legal control, not a convenience.

## 7.4 Decisions this document needs

1. **S1 — authoring layer in the window, or v1.1?** Everything in §5.8, §5.12 and borrows #6/#11 hangs on this. Given W0's verdict (~120 h of design funded with ~35), my recommendation is **v1.1 for generation, but land `agent` + `agent_config_version` + `test_case`/`test_category` now**, because F4 and W1 §9.1 need them regardless and they are ~4 h of the 10-table estimate.
2. **The two probes, before any `RunEngine` code** — Vapi concurrency queueing, and a 3-beat reactive spine against the live Riley assistant (F6). ~30 min, ~$0.25.
3. **Vapi prompt exposure** — adopt W2 C1's `prompt_access` and restate the trust claim, or drop the claim.
4. **Retell in or out** (W0 cut #1 says out).
5. **Accept the loopback transport as hour-1 P0** (three passes agree).
6. **Composite score formula, GitHub Action, PR comment** — still unwritten anywhere.
7. **Audio-native judge in v1** — note that a competitor now ships voice testing, which weakens the "no reviewer can evaluate it" argument.
8. **Fold W0 into W1 as a §12 corrections table, name W2 in W1's header, add a dated decisions log, retire W3 as a source** — the README's own 90-minute merge. This document is written against the four-doc set; every hour that set stays unmerged is an hour someone can implement F6 or the `export_call` view in good faith.

---

## §8. The principle, as a review rule

> **Wiretap's docs define WHAT we build. LangWatch shows HOW a mature system solved adjacent problems.**

A proposal that cites LangWatch must answer four questions:

1. **Which Wiretap document and section does this serve?** No citation ⇒ scope creep, however good the pattern. (Note the authority order: W0 > W1 > W2 > W3. Citing `PRD-STALE.md` alone is not a citation.)
2. **Pattern or mechanism?** Patterns transfer — versioned projections, result contracts, immutable version rows, content-addressed payloads, staging-before-finalize. Mechanisms usually don't — ClickHouse, BullMQ, worker pods, OTel.
3. **What is the simplest form that keeps the property?** Event sourcing → append-only tables + `run_score`. Projection replay → one verb with a dry-run. Foundry → a fixture adapter. Dataset staging → one table and a screen.
4. **Now or later?** "Cheap now, expensive later" (three nullable columns, one hash column) → now. "Only makes v1.2 possible" (`judge_vote`) → later.

And the asymmetry to keep hold of: LangWatch is a **hosted, multi-tenant, general-purpose** platform observing systems its users already own. Wiretap is a **local, single-user, single-purpose** tool firing adversarial traffic at systems its users must *prove* they own, on a 35-hour budget against a ~120-hour design. Wiretap's architecture is not a simplification of LangWatch's; it is a different architecture that shares some data-modelling vocabulary. Every borrow above is a vocabulary borrow, and every one of them has to survive a cut list first.

---

## Appendix A — Sources

**Wiretap (source of truth), `~/wiretap-docs/`:** `README.md` (2026-08-12) · `REVIEW-FINDINGS.md` (2026-08-11, F1–F18 + cut list + missing + riskiest assumption) · `ARCHITECTURE.md` (2026-08-10, 11 sections, live-verified) · `SUITE-LIFECYCLE.md` (2026-08-10, C1–C3, 10 tables, 5-stage pipeline, E1–E8, S1–S4) · `PRD-STALE.md` (2026-08-05, superseded) · `probes/` (`probe_vapi.py`, `probe_pyai.py`, `p1_ceiling.py`, `p1_disambiguate.py`, `rate_limits.py`, `selftest.py`, `erd.mmd`).

**LangWatch (reference), retrieved 2026-08-12.** Repo/releases: `github.com/langwatch/langwatch` (Apache-2.0 + `ee/`, ~3.5k stars; v3.12.0 2026-08-10, v3.11.0 2026-08-09 breaking, `agent-plugin` v1.0.0, `typescript-sdk` v1.4.0) · `github.com/langwatch/scenario`.
Docs: `/docs/introduction` · `/concepts` · `/observability/overview` · `/observability/trace-vs-activity-ingestion` · `/integration/python/guide` · `/evaluations/overview` · `/evaluations/evaluators/list` · `/evaluations/evaluators/custom-scoring` · `/evaluations/experiments/overview` · `/evaluations/experiments/multimodal-evaluation` · `/datasets/overview` · `/datasets/ai-dataset-generation` · `/features/annotations` · `/ai-gateway/overview` · `/prompt-management/data-model` · `/api-reference/scenario-events/overview` · `/api-reference/simulation-runs/overview` · `/self-hosting/overview` · `/self-hosting/infrastructure/architecture` · `/self-hosting/licensing` · `/self-hosting/ops/overview` · `/docs/llms.txt` · `/changelog` · `/pricing` · `/trust-center`.
Blog: "Testing Voice Agents with LangWatch Scenario in Real Time" · "LangWatch Skills" · their own four-way comparison.
Third-party: MarkTechPost 2026-08-09 platform comparison; EU-Startups / Silicon Canals on the €1M pre-seed (Passion Capital, Volta Ventures, Antler; founded 2023 by Manouk Draisma and Rogerio Chaves).

**Could not verify:** Scenario's licence and star count (W1 §3.1 says 950★) · whether LangWatch recomputes historical cost via projection replay (mechanism documented, application to cost not) · `SimulationRun`'s field schema (not published) · how annotations feed datasets (undocumented) · Scenario's voice capability matrix (URL 404s) · the AI generator's prompt, rejection taxonomy, and per-record provenance fields (shape documented, details not).

## Appendix B — Consolidated open items

| # | Item | Source | Blocks |
|---|---|---|---|
| 1 | S1 — authoring layer now or v1.1 | W2 §9 | 10 tables, 16–52 h |
| 2 | Vapi concurrency-queueing probe | W0 riskiest | 50-tile grid honesty; every latency number |
| 3 | 3-beat reactive spine probe (F6) | W0 | Highest-frequency runtime bug |
| 4 | Vapi prompt exposure → adopt C1? | W1 §3.1, W2 C1 | Public trust claim |
| 5 | Retell in or out | W1 §10 Q1, W0 cut #1 | 8–12 h |
| 6 | Loopback transport accepted as P0? | W0, README, §5.14 | 9 of 14 gates |
| 7 | Composite score formula / Action / PR comment | unwritten | Card + CI |
| 8 | Audio-native judge in v1 | W3 §2.2 vs conversation | Judge surface |
| 9 | S2 — corpus as YAML or rows (I recommend rows, §5.8) | W2 §9 | One code path or two |
| 10 | S3/S4 — extraction quality at `prompt_access='none'`; template ownership | W2 §9 | Retell UX; C2 enforcement |
| 11 | `unclear` in κ (if `dispute` returns) | W3 §9.4 | A published number |
| 12 | Who writes the 50 personas, and when | W0 missing | Grid + card critical path |
| 13 | Migrations, `resume`, `reap`, `prune`, error taxonomy, backpressure, byte counters | W0 missing | Day-two failures |
| 14 | Fold W0 into W1; name W2 in W1's header; decisions log; retire W3 | README | Everyone reading the set |
