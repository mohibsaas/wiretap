# Wiretap — Staff Engineering Review of ARCHITECTURE.md

**Date:** 2026-08-11 · **Reviewer:** staff-level adversarial design review
**Subject:** `ARCHITECTURE.md` draft 1 (2026-08-10) + the five probe scripts
**Status:** findings NOT yet applied to `ARCHITECTURE.md`

> This file exists because these findings previously lived only in a
> conversation and an ephemeral task file, which has since been deleted. The
> LangWatch research pass (2026-08-12) was written without them and several of
> its recommendations rest on defects listed here. Do not review or extend
> `ARCHITECTURE.md` without reading this first.

---

## Verdict

Not buildable in 33 hours as specified. The vendor research is sound and the
live-verified facts are load-bearing, but the architecture on top of it is a
~120-hour product design funded with ~35 engineering hours, and three defects
specifically break the four promised demo deliverables.

**Single biggest problem:** the reproducibility claim — the headline — is not
computable from the schema.

---

## Findings, most severe first

### F1 — The run-twice-same-hash demo is unqueryable
**§5 + §8.5 `audio_artifact`.** §5 states the guarantee as "identical
caller-audio SHA-256 set". `audio_artifact` is keyed only by `call_id`, and
`beat_cache` rows are per-beat and shared across calls — so they either get NULL
`call_id` (orphaned, never cascaded) or are duplicated per call. Either way
there is no `WHERE run_id = ?` that yields the set. `run.replication_sha256`
hashes *config*, not audio. No `wiretap verify` command is specified anywhere.

**Fix:** add `run_id TEXT NOT NULL` to `audio_artifact`; add
`run.caller_audio_set_sha256` = sha256 of sorted-concatenated `beat_cache`
digests, computed at audio-prep time before any call is dialed.

### F2 — Three clocks feed one timeline, never reconciled
**§8 preamble vs `turn`, `wire_event.t_ms`, `tool_call.t_invoked_ms`.**
Preamble says "all timestamps are integer epoch milliseconds". `turn`'s comment
says anchors are `time.monotonic` (arbitrary per-process epoch, not epoch-ms,
not comparable across processes). `tool_call.t_invoked_ms` is "retell `time_sec`
× 1000" — seconds since call start, a third base. `wire_event.t_ms` declares no
base. The timeline deliverable cannot place these on one axis.

**Fix:** rename intra-call columns to `t_rel_ms` = offset from
`call.started_at`; add `call.t0_monotonic_ns` as the conversion anchor; make
`call.started_at` the only epoch value in call scope. Also "four anchors"
describes two columns — leftover text.

### F3 — `UNIQUE (run_id, persona_id, attempt)` forbids required repeats
**§8.2 `call`.** Verified in SQLite: three rows with NULL `persona_id` insert
cleanly (NULLs are distinct, so the constraint is vacuous in `mode='observed'`,
which is exactly when `persona_id` is NULL); and a second row for the same
persona at `attempt=1` raises IntegrityError. §5 promises measured score
stability, which requires running the same persona N times — blocked unless you
abuse `attempt`, which §8.2 reserves for infra retries.

**Fix:** `UNIQUE (run_id, seq)` plus `repeat_index INTEGER NOT NULL DEFAULT 0`.
Make `persona_id` NOT NULL and cut `observed` mode.

### F4 — No category, tier, or persona table: the report card's rollups have no source
**§8 entire.** The card needs per-category and per-difficulty-tier rollups.
There is no `category`, no `difficulty`, no `tier`, no `persona` table. `call`
carries only `persona_id TEXT`. Both rollups would require re-reading YAML off
disk; once a persona file changes, `persona_sha256` detects drift but nothing
recovers what the category *was*, so old runs become un-rollup-able.

**Fix:** `persona` (or `test_case`) table written at suite-resolution time;
denormalize `category` and `difficulty_tier` onto `call`.
*(Also resolved by `SUITE-LIFECYCLE.md` §3.1's `test_case` + `test_category`.)*

### F5 — No stored scores: `compare` silently re-scores history
**§8.3.** `assertion_result` has `blocking` but no weight, and there is no
`run_score` table. The grade is recomputed at render time. Change the scorer and
every prior run's grade silently changes.

**Fix:** `run_score (run_id, scope_kind ∈ {run,category,tier}, scope_key, score,
n_pass, n_fail, n_not_executed, scorer_version)`. Refuse comparison across
differing `scorer_version`.

### F6 — Event bus has a lost-wakeup deadlock
**§6 TX pseudocode `await event_bus.wait(beat.after)`.** RX emits
`agent_speech_end` on a 250 ms hangover. If that fires while TX is inside
`sleep(beat.delay_ms)` or still streaming the previous beat, the edge is lost
and TX waits for the next `agent_speech_end` — which never arrives, because the
agent is waiting for the caller. The call burns to the duration cap in silence
and reads as an agent timeout. Highest-frequency runtime bug in the design;
invisible in code review.

**Fix:** append-only sequence, not an `Event`. TX holds a cursor and awaits
`bus.wait_after(cursor, kind)`. Every beat gets a mandatory `timeout_ms`
fallback that fires anyway and stamps `turn.trigger='timeout'`.

### F7 — The beat spine cannot express barge-in
**§6 vs `turn.interrupted`.** `beat.after` is only ever shown waiting on
`agent_speech_end`. An interrupter persona must speak *during* agent speech.
There is no "N ms after `agent_speech_start`" trigger, so `turn.interrupted` has
no producer and the nightmare-caller archetype most likely to break an agent
cannot be scripted.

**Fix:** `beat.after ∈ {agent_speech_start, agent_speech_end, caller_beat_end}`
plus `after_ms`. ~10 lines.

### F8 — `export_call` cannot support the timeline
**§8.7.** "The publish path must query this view and nothing else." The view
exposes eight columns of `call`. The timeline needs `turn`, `turn_transcript`,
`assertion_result`, `wire_event`. Either the timeline is unpublishable or the
rule is violated on day one. A view is also the wrong mechanism.

**Fix:** drop the view; one serializer module with a test asserting the
serialized keyset equals a frozen literal. ~20 minutes.

### F9 — PII quarantine is the largest hidden cost and buys nothing for the demo
**§8.6.** `start_offset`/`end_offset` don't state whether they index raw or
redacted text, and cannot be both (`[PII:PERSON_NAME]` is 18 chars, `Bob` is 3).
`origin_ref INTEGER` is a polymorphic FK where `origin='transcript'` points at
`turn_transcript`, whose PK is the composite `(turn_id, source)` — unreferenceable
by an integer — and `origin='vendor_summary'` references a table that doesn't
exist. `PERSON_NAME` needs NER (model download, thread pool, new failure mode).

**Fix for the window:** cut it. Regex pass at export time plus a banner: "not
PII-safe; do not point at production." Recovers ~6–10 h of 35.

### F10 — Evidence offsets don't identify which transcript they index
**§8.3.** `evidence_turn` + "offsets into `text_redacted`", but `turn_transcript`
holds up to four rows per turn with different text and different offsets. The
pinned timeline flag highlights the wrong span whenever sources differ.

**Fix:** add `evidence_source TEXT NOT NULL`, FK to `(turn_id, source)`.

### F11 — Cost cannot be settled, and the schema forbids "unknown"
**§8.5 vs §9.1.** §8.5 says unsupported cost is never stored as 0. §9.1 verified
Vapi reports exactly `cost: 0, status: in-progress` at teardown.
`cost_ledger.amount_usd` is `REAL NOT NULL`, so you must write the forbidden 0.
No poll state, no `run.cost_settled`, nothing stopping the card rendering a
total while `settled=0` rows exist. Separately, PyAI `/v1/me` credit doesn't
move in real time — so **BudgetGovernor has no real-time spend signal from
either vendor** and is necessarily estimating.

**Fix:** `amount_usd` nullable with `basis='unsettled'`; add `run.cost_settled`;
state plainly that enforcement is an estimate and §6.2's overshoot formula is
the only guarantee.

### F12 — §4.4's "only CPU work on the event loop" is contradicted and aimed wrong
**§4.4 vs §6 RX pseudocode.** RX is `append_pcm(disk); rms = rms_20ms(frame)` —
a synchronous file write immediately before the thing declared to be the only
permitted work.

Measured on this machine: pure-Python `struct`+`sum` RMS is **8.6 µs/frame** =
**0.43% of one core** at 10 concurrent. A simulated 20-call run (20 pacers + 20
RX loops with RMS + disk append + a 14 KB JSON parse per second) held 20 ms
pacing at **p99 = 2.25 ms jitter**. RMS is not the constraint. (`audioop` was
removed in Python 3.13; this box runs 3.14, so the C fast path is gone —
irrelevant given the numbers.)

**What actually breaks first:** an unbounded writer queue behind a serialized
SQLite writer; a blocking `fsync` stalling all pacers; and JSON-parsing Vapi's
`conversation-update`, which carries the **full 9,304-char system prompt on
every final transcript** (~14 KB/frame, ~1,000 frames/run → **~14 MB of
duplicated prompt** into `wire_event.payload_redacted`).

**Fix:** rewrite §4.4 to name the real risks; buffer PCM to ~1 s chunks; bound
the writer queue and drop `wire_event` first under pressure; store
`conversation-update` payloads as a `sha256 → text` dedup reference. Extend
§8.8's denylist to cover the customer's system prompt.

### F13 — No behaviour defined when a socket dies mid-beat; no read timeout
**§6 "exit on socket close".** With two coupled tasks, nothing says who cancels
the peer, writes terminal status, drains the writer queue, or releases the
concurrency slot. Half-open sockets (no FIN — routine behind Cloudflare, already
confirmed to front Vapi) leave RX blocked in `recv()` forever. No
`ping_interval`/`ping_timeout`, no wall-clock deadline task. One hung call holds
a slot permanently and the run never reaches `complete` — so per §6.1 **no grade
renders at all**.

**Fix:** one `asyncio.TaskGroup` per call;
`websockets.connect(..., ping_interval=5, ping_timeout=10)`; a hard deadline
task in the group; semaphore released in `finally`; terminal status written by
the group owner, not either leg.

### F14 — Harness latency has an undocumented systematic bias
**§4.4 + §8.5.** `agent_speech_end` fires 250 ms after audio stops (hangover) and
onset is quantized to 20 ms windows. Every harness number carries a fixed
+250 ms bias and ~20 ms quantization. `latency_metric` records `source='harness'`
but not threshold or hangover, so numbers aren't comparable across a threshold
tweak — and someone will tweak it at 3am.

**Fix:** store `rms_threshold` and `hangover_ms` on `run`; subtract
`hangover_ms` when stamping `turn.t_end_ms`; state the quantization floor next
to any p95.

### F15 — Missing indexes (low severity)
`latency_metric` has no index at all (p95 needs a full scan); `cost_ledger` none
on `run_id` (hit between every call); `turn` is indexed `(call_id, seq)` but the
timeline orders by time, and with barge-in `seq` order ≠ time order. None bite at
50 calls. Add `idx_latency ON latency_metric(call_id)` and
`idx_turn_time ON turn(call_id, t_start_ms)`.

### F16 — Dead enum contradicting the doc's own correction
**§8.5 `throttle_event.kind`** includes `'ws_4429'`. §3.1 corrects the PRD to say
that branch never fires. Delete it or the next reader writes the handler.

### F17 — "No server" vs `wiretap serve`
**§2.** "No Docker, no server, no account" immediately followed by "`wiretap
serve` is the same process serving static assets and an SSE stream." That is a
server. SSE at 50 tiles on conference wifi has real failure modes (proxy
buffering, connection cap, reconnect-on-sleep) that "no server" invites you not
to plan for.

### F18 — Economics omit transcription and understate the judge
**§11.** The harness line is "~$0.01/min · ~$1" for judge + one-time TTS. 150
minutes of audio must go through `whisper-pinned` — local (tens of minutes of
wall-clock post-run, delaying the card, not costed in time) or hosted (not
costed in dollars). ~8 assertions × 50 calls × multi-thousand-token transcripts
is 1M+ judge input tokens, several times $1. The wall-clock one is the schedule
risk.

---

## Cut list (ordered; cut from the top until 35 hours fits)

1. **Retell adapter** — §10 Q1 admits "200 lines or 8–12 h of WebRTC"; every
   Retell row in §3 is unverified. Ship Vapi + `local-demo`.
2. **LIVE mode / `pyai-omni` caller** — §10 Q6: `persona_perspective` could not
   be reproduced in five configurations. §5 already says LIVE isn't publishable.
3. **`pii_quarantine` + detect-before-write** (F9).
4. **`dispute` + tune/holdout splits.**
5. **`judge_cache`** — the doc's own comment says hit rate is low against a live
   agent. Keep `assertion_result.judge_cache_hit` defaulted 0 for v2.
6. **`tool_call` table** — its only verified producer is Retell, now cut.
7. **`transcriber_secondary` + dual-ASR divergence** — keep `ground_truth` vs
   `pinned_whisper`; that one is the genuine differentiator and it's free.
8. **`throttle_event`** — §7 says neither rate limit binds at 50 calls.
9. **`latency_metric`** — collapse to `turn.t_response_ms`, `turn.t_stop_ms`,
   `call.vendor_latency_json`.
10. **`cost_ledger`** — four REAL columns on `run` + one post-run poll.
11. **`run_capability`** — one adapter per run; a JSON blob on `run`.
12. **`export_call` view** (F8) — serializer allowlist + one test.
13. **`mode='observed'`** — sole reason `persona_id` is nullable, which makes
    F3's UNIQUE vacuous.
14. **MCP client surface** — ship CLI and UI.

16 tables → **8**: `run`, `persona`/`test_case` (new, F4), `call`, `turn`,
`turn_transcript`, `assertion_result`, `audio_artifact`, `run_score` (new, F5),
plus `wire_event` and `attestation` (both one-insert-cheap).

---

## Missing entirely

- **`local-demo` loopback adapter as hour-1 work, not a footnote.** A socket
  echoing a canned WAV lets you develop and demo the 50-wide grid, timeline,
  scoring and the hash claim at zero cost, zero network, zero vendor ceiling. It
  derisks every cut above and answers "50 tiles when Vapi allows 10."
- **Schema migrations.** No `PRAGMA user_version`, no runner, no `db reset`. Two
  engineers editing 16 tables against a shared `./data/wiretap.db` diverge by
  hour six.
- **Resume of a partial run.** Crash at call 40/50 and §6.1 forbids rendering any
  grade — money spent, no card. `wiretap run --resume <run_id>` skipping
  terminal-status calls is ~30 lines of demo insurance.
- **SIGKILL / orphaned vendor calls.** WAL saves the DB; it does not hang up ten
  in-flight calls, which keep billing and holding slots. Need `wiretap reap
  <run_id>` plus a signal handler.
- **Error taxonomy.** `call.status='error'` + free-text `retry_reason`, no enum
  for `connect_refused | auth_403 | concurrency_reject | ws_abnormal_close |
  no_audio_rx | beat_timeout | transcribe_failed | judge_failed`. Without it the
  grid can't colour-code and triage is grep.
- **Harness self-observability, especially a silent-drop guard.** §4.2 verified
  PyAI drops untagged frames with no error, no log, no counter. The harness must
  not share that property. Add `call.tx_bytes`, `call.rx_bytes`,
  `call.pacer_underruns`, and the invariant `tx_bytes > 0 AND rx_bytes > 0` or
  the call is `error`, never `failed`.
- **Backpressure.** No bounded queue anywhere — writer queue, event bus, RX PCM
  buffer all unbounded.
- **Disk growth.** ~11.5 MB/call × 50 = **~600 MB per run** of raw PCM plus
  vendor recordings. No retention, no compression, no `gc`. Ten dev runs is 6 GB.
- **A determinism verification command.** The claim is "run twice, same hash";
  no `wiretap verify <run_a> <run_b>` exists, and per F1 the data isn't there.
- **Who writes the 50 personas, and when.** A day of PM/designer time, on the
  critical path for both the grid and the card, absent from the doc.
- **Testing strategy for the harness itself.** Zero mention. Minimum: a
  golden-transcript fixture through the scorer, and a fake socket replaying the
  recorded `out/agent_leg.wav` + `text_frames.json` already on disk.

---

## Riskiest assumption

**§10 Q2 — that `vapi.websocket` calls do not silently queue against the
concurrency ceiling.** Unverified, and load-bearing twice: if Vapi queues (its
documented overflow behaviour), then (a) the 50-tile grid is a lie, because
tiles 11–50 sit in a vendor queue while rendering as in-flight, and (b) every
latency number is invalid, because `concurrency_blocked` and `latency_valid` can
only be set from a signal the harness never receives. Discovered on day two,
neither is fixable inside the window.

**Cheap test, ~15 minutes, ~$0.25, mostly already written:** extend
`probe_vapi.py` to `POST /call` twelve times, open all twelve sockets, record
time-to-first-downlink-byte per call. Flat TTFB across twelve → true
parallelism, grid is honest. Step change after the tenth → silent queueing; set
`latency_valid=0` above the ceiling and cap the live grid at 10 real tiles. Do
this before writing a line of `RunEngine`.

**Runner-up, same hour:** F6's lost-wakeup. Run a 3-beat reactive spine against
the Riley assistant already provisioned. If beat 2 never fires, you've found it
on day zero instead of during the demo.
