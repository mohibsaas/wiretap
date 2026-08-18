# Robustness

This document covers Wiretap's resilience patterns: error handling, retries, failure classification, concurrency limits, isolation guarantees, and known failure modes.

---

## 1. Design philosophy

Wiretap tests **live external systems** (voice agents, LLM APIs, speech providers, telephony). Failures are expected and must be classified correctly:

- **Agent failure** — the deployed agent behaved incorrectly → scored as fail/partial
- **Harness fault** — Wiretap's test caller, STT, judge, or transport broke → scored as **inconclusive**
- **Transient outage** — retried automatically where safe; surfaced clearly when exhausted

The guiding rule: **never blame the agent for Wiretap's mistakes.**

---

## 2. Failure classification

### 2.1 Verdict types

| Verdict | Meaning | Counts against agent? |
|---------|---------|------------------------|
| `pass` | Goal met, rules satisfied | No (success) |
| `partial` | Partial goal match (0.5–0.7) | Yes (soft fail) |
| `fail` | Goal not met or rules violated | Yes |
| `inconclusive` | Harness or judge could not produce a valid score | **No** |

### 2.2 Inconclusive triggers

A scenario is marked inconclusive (not agent fail) when:

| Condition | Module | Rationale |
|-----------|--------|-----------|
| LLM judge API failure | `eval/judge.py` | Cannot score without judge |
| Invalid regex in rules | `eval/rules.py` | Rule config error, not agent behavior |
| STT failure on voice transport | `transport/turn_gate.py` | Harness couldn't hear the agent |
| Strict caller contract violation | `eval/meta.py` | Test agent went off-script (--strict mode) |
| Scenario timeout | `agent/simulate.py` | External hang, not agent quality |
| Transport connection failure | `transport/*` | Dial infrastructure issue |

---

## 3. Retry patterns

### 3.1 HTTP retries (`providers/http_retry.py`)

Speech provider and catalog HTTP calls use `with_http_retries()`:

```text
Attempts:     4
Base delay:   0.6s (exponential backoff, cap 12s)
Retry on:     408, 429, 500, 502, 503, 504
              + TimeoutException, TransportError
Respects:     Retry-After header
Never logs:   Response bodies (may contain account details)
```

### 3.2 Tool-call evidence fetch

Post-call tool evidence collection (Retell, Vapi, ElevenLabs):

```text
Attempts:     3
Delay:        2s between attempts
Permanent:    401, 403 → no retry (auth failure)
Transient:    429, 5xx, timeouts → retry
```

### 3.3 LLM judge

Judge calls go through LiteLLM. Failures produce an inconclusive verdict rather than a fail. Temperature is pinned at **0.0** to minimize score drift across runs.

---

## 4. Timeout handling

| Scope | Default | Override |
|-------|---------|----------|
| Per-scenario | 240s (CLI/UI) | `--timeout` flag |
| MCP simulate | 900s | Built into MCP tool |
| HTTP per-request | Provider default | httpx client timeouts |

Scenarios exceeding the timeout are cancelled via `asyncio.wait_for`. The transport `hangup()` runs in a `finally` block regardless of timeout or exception.

---

## 5. Concurrency and rate limiting

### 5.1 Provider-aware caps (`eval/concurrency.py`)

```text
Voice platforms (Retell, Vapi, ElevenLabs, LiveKit, Synthflow, Bland, Bolna): 2
PSTN (Twilio SIP):                                                          1
Text / CI stub:                                                             32
```

**Why caps exist:** High parallel WebRTC/LiveKit dials cause connection timeout storms and empty evaluation batches. These are soft provider quotas, not Wiretap bugs.

### 5.2 Override behavior

| Flag | Effect |
|------|--------|
| Default | Request clamped to provider cap with explanatory note |
| `--force-concurrency N` | Override voice cap with warning about expected timeouts |
| PSTN | **Cannot override** — single SIP registration is a hard limit |

### 5.3 Semaphore isolation

Parallel scenarios share an `asyncio.Semaphore` but **never share session state**:

- Each scenario gets its own transport instance
- Each scenario gets its own orchestrator
- Each scenario writes its own artifact
- Batch execution uses `asyncio.gather(..., return_exceptions=True)` — one failure does not crash the batch

---

## 6. Transport resilience

### 6.1 Hangup guarantee

```python
# simulate_scenario — simplified
try:
    # turn loop
    ...
finally:
    await transport.hangup()
```

Every simulation path — success, timeout, exception — triggers transport cleanup.

### 6.2 Voice activity detection (AgentTurnGate)

Voice transports use shared VAD + batch STT for endpointing:

- Detects agent speech silence before triggering test-agent reply
- Prevents premature responses during agent pauses
- STT failures → inconclusive (not agent fail)

### 6.3 Transcript selection

After hangup, Wiretap may fetch a provider "final transcript" (Retell, Vapi). The judge uses the best available transcript via `pick_judge_transcript()` — preferring provider-final when quality is higher, falling back to live STT transcript.

### 6.4 TTS prefetch

Voice transports prefetch PCM audio for the next test-agent utterance while waiting for the agent reply, reducing perceived latency. Prefetch failures fall back to on-demand synthesis.

---

## 7. Batch execution resilience

### 7.1 In-memory batch state

UI batches (`services/batches.py`) hold progress in memory:

| Property | Behavior on server restart |
|----------|---------------------------|
| Batch metadata | Lost |
| Progress events (SSE) | Lost |
| Disk artifacts (JSONL) | **Preserved** |
| Progress sidecars (`*.progress.json`) | **Preserved** |

Disk artifacts survive restarts. Only the in-memory SSE stream and batch registry are ephemeral.

### 7.2 Progress durability

Progress files use atomic writes:

```text
Write to temp file → os.replace() to target path
```

Shared between CLI and UI — either surface can write progress; both can read it.

### 7.3 Advisor isolation

The optional run-level LLM advisor (`eval/advisor.py`) is **additive only**:

- Runs after all scenarios complete
- Failures are logged but never modify run results
- Never changes verdicts or scores

---

## 8. Evaluation robustness

### 8.1 Deterministic rules

Rules run before the LLM judge:

| Rule type | Behavior on error |
|-----------|-------------------|
| `includes` | Missing phrase → fail |
| `excludes` | Found phrase → fail |
| `patterns` (regex) | Invalid regex → **inconclusive** (not fail) |

Regex compilation errors are harness config faults, not agent behavior.

### 8.2 Strict mode (`--strict`)

When enabled:

- Lower simulator temperature for more predictable test-agent behavior
- Caller contract check flags when the test agent deviates from persona/goal
- Contract violations → **inconclusive** (the test was bad, not the agent)

### 8.3 Regression detection

After scoring, Wiretap compares against the latest passing baseline for the same scenario:

- Previously passing + now failing → regression flag
- No baseline → no regression check
- Baseline lookup scans daily JSONL files (linear scan)

Regression is informational — it does not change the verdict.

### 8.4 Tool verification

When the platform exposes post-call tool evidence:

- Expected tools from scenario config vs observed tools from provider API
- Mismatch contributes to evaluation but platform API unavailability → graceful skip (not fail)

---

## 9. Secret and config safety

| Pattern | Implementation |
|---------|----------------|
| Secret storage | `~/.wiretap/.env` only; chmod 600 on write |
| API responses | Return bool status, never secret values |
| Suite YAML | IDs + `token_env` names only |
| HTTP logging | Never log response bodies in retry/catalog modules |
| Input validation | `validate_suite_name()` blocks path traversal |
| Secret writes | Managed key allowlist; regex validation on key names |
| Prompt apply | Hash check before PATCH; redacts secret patterns |
| AgentGraph IR | Strips webhook URLs, auth headers, tokens from imports |

---

## 10. MCP robustness

| Concern | Mitigation |
|---------|------------|
| Stdout pollution | MCP uses stdout for JSON-RPC; all prints redirected to stderr |
| Path validation | Tools validate suite names against path traversal |
| Long timeouts | MCP simulate uses 900s timeout (vs 240s CLI default) |
| Error surfacing | Tool errors return structured messages, not stack traces |

---

## 11. Known failure modes

### 11.1 Expected failures (operational)

| Failure | Symptom | Mitigation |
|---------|---------|------------|
| Provider rate limit (429) | Retries then inconclusive/transport error | Lower `--concurrency`; respect caps |
| LiveKit connection timeout | Empty transcript, inconclusive | Reduce parallel dials; check agent is deployed |
| LLM provider outage | Inconclusive verdict | Retry later; check API key |
| STT misrecognition | Wrong transcript → possible false fail | Review audio artifact; try different STT provider |
| Judge non-determinism | Score varies slightly between runs | Temperature 0.0 mitigates; accept probabilistic nature |
| PSTN registration conflict | Second parallel call fails | Hard cap at 1; expected behavior |

### 11.2 Structural limitations

| Limitation | Impact | Workaround |
|------------|--------|------------|
| JSONL artifact store | Linear scan for lookups; no indexing | Export/report commands; future DB if needed |
| In-memory batch state | UI progress lost on restart | Disk artifacts + progress sidecars survive |
| Single-process asyncio | No horizontal scaling | Run multiple CLI instances with different suites |
| No circuit breaker | Repeated provider failures keep retrying | Manual backoff; lower concurrency |
| No dead-letter queue | Failed scenarios logged in batch, not requeued | Re-run failed scenarios manually |
| LLM judge cost | Every scenario calls judge LLM | Use cheaper judge model; filter scenarios |

---

## 12. Failure mode decision tree

```text
Scenario execution starts
        │
        ├── Transport connect fails?
        │     └── YES → inconclusive (dial failure)
        │
        ├── Turn loop runs
        │     ├── STT failure?
        │     │     └── YES → inconclusive (harness fault)
        │     ├── Timeout?
        │     │     └── YES → inconclusive (hang)
        │     └── Completes normally
        │
        ├── Caller contract violation (--strict)?
        │     └── YES → inconclusive (bad test agent)
        │
        ├── Rules check
        │     ├── Invalid regex?
        │     │     └── YES → inconclusive (config error)
        │     └── Rule fail → verdict: fail
        │
        ├── LLM judge
        │     ├── Judge API failure?
        │     │     └── YES → inconclusive
        │     └── Score → pass / partial / fail
        │
        └── Regression check (informational)
```

---

## 13. Recommendations for reliable runs

1. **Start with concurrency 1–2** for voice platforms; increase only after confirming stability
2. **Use `--strict` in CI** to catch test-agent drift early
3. **Pin judge model** in suite YAML for consistent scoring
4. **Review inconclusive results** separately from fails — they indicate harness or infra issues
5. **Keep audio artifacts** for disputed scores — WAV files enable manual review
6. **Use text transport in CI** for fast, cost-free pipeline checks (rules + judge without voice)
7. **Monitor API key quotas** — Wiretap retries but cannot bypass hard provider limits
8. **Export suites to git** for reproducible CI runs with version-controlled test definitions
