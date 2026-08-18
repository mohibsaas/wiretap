# Production Readiness

This document assesses Wiretap's readiness for different deployment contexts: local developer QA (current sweet spot), CI/CD integration, and hypothetical hosted-service deployment.

---

## 1. Deployment context matrix

Wiretap is designed as a **local-first developer tool**. Production readiness depends on how you deploy it:

| Context | Readiness | Notes |
|---------|-----------|-------|
| Developer laptop (manual QA) | **Ready** | Primary use case; fully supported |
| CI/CD pipeline (automated regression) | **Ready with setup** | User provides pipeline; no in-repo CI template |
| Team-shared local instance | **Partial** | UI has no auth; bind localhost only |
| Hosted multi-tenant SaaS | **Not ready** | Significant hardening required (see §6) |

---

## 2. Local developer deployment

### 2.1 Installation

```bash
git clone https://github.com/mohibsaas/wiretap.git
cd wiretap
uv sync
uv tool install --editable .

# Optional: PSTN support
uv sync --extra pstn

# Optional: MCP server
uv sync --extra mcp

# Build UI
cd ui && npm install && npm run build && cd ..
```

### 2.2 First run

See **[setup.md](./setup.md)** for the full first-time guide (prerequisites, required keys by platform, interactive vs manual setup).

```bash
wiretap init          # Wizard: simulator → agent → suite → phone
wiretap status        # Verify config (no secret leakage)
wiretap simulate --all
wiretap report
```

### 2.3 Data directory

All state lives in `~/.wiretap/`:

| Path | Contents | Backup needed? |
|------|----------|----------------|
| `.env` | API keys and secrets | Yes — store securely |
| `suites/` | Test definitions | Yes — or export to git |
| `simulations/` | Call artifacts (JSONL + WAV) | Optional — may contain PII |
| `evaluations/` | Batch summaries | Optional |
| `graphs/` | Imported AgentGraph IR | Regenerable via import |
| `onboard.json` | UI preferences | Low priority |

Override with `$WIRETAP_HOME=/path/to/data`.

### 2.4 Local UI

```bash
wiretap ui run                    # http://127.0.0.1:8787
wiretap ui run --host 0.0.0.0    # ⚠ UNSAFE — exposes secrets API
```

**Always bind to localhost** unless you add authentication (not shipped).

---

## 3. CI/CD integration

Wiretap does not ship a GitHub Actions workflow. Integrate into your existing pipeline:

### 3.1 Recommended CI pattern

```yaml
# Example GitHub Actions workflow (user-provided, not in repo)
name: Voice agent regression

on:
  push:
    branches: [main]
  pull_request:

jobs:
  voice-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install wiretap
        run: |
          uv sync
          uv tool install --editable .

      - name: Configure secrets
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          PYAI_API_KEY: ${{ secrets.PYAI_API_KEY }}
          RETELL_API_KEY: ${{ secrets.RETELL_API_KEY }}
        run: |
          mkdir -p ~/.wiretap
          cat > ~/.wiretap/.env <<EOF
          OPENAI_API_KEY=$OPENAI_API_KEY
          PYAI_API_KEY=$PYAI_API_KEY
          RETELL_API_KEY=$RETELL_API_KEY
          EOF
          chmod 600 ~/.wiretap/.env

      - name: Copy test suites
        run: cp -r ./test-suites/* ~/.wiretap/suites/

      - name: Run simulations
        run: |
          wiretap simulate --suite my-agent --all \
            --concurrency 1 \
            --transport text    # fast CI stub, or web for live dials
        timeout-minutes: 30

      - name: Check results
        run: |
          wiretap report --suite my-agent
          # Exit non-zero if any scenario failed
          wiretap report --suite my-agent --json | \
            python -c "import sys,json; r=json.load(sys.stdin); sys.exit(1 if r.get('failed',0)>0 else 0)"
```

### 3.2 CI best practices

| Practice | Rationale |
|----------|-----------|
| Use `--transport text` for fast/cheap checks | No voice dial cost; tests rules + judge logic |
| Reserve live voice dials for nightly/scheduled runs | Voice calls cost money and time |
| Set `--concurrency 1` in CI | Avoid provider rate limits in shared CI environments |
| Store suites in git via `wiretap export` | Reproducible, version-controlled test definitions |
| Use `--strict` mode | Catch test-agent drift; inconclusive on harness faults |
| Set scenario timeouts explicitly | Prevent hung CI jobs |
| Archive simulation artifacts as CI artifacts | Enable post-hoc debugging |
| Never commit `.env` files | Use CI secret stores |

### 3.3 Exit codes

| Code | Meaning |
|------|---------|
| 0 | All scenarios passed (or no failures above threshold) |
| Non-zero | One or more scenarios failed |

Use `wiretap report --json` for programmatic pass/fail gates.

### 3.4 Cost management

Each live voice simulation incurs:

- LLM tokens (simulator + judge per turn)
- STT/TTS API calls (per utterance on voice transports)
- Platform dial minutes (Retell, Vapi, etc.)
- Twilio minutes (PSTN)

Budget accordingly. Text transport eliminates STT/TTS/dial costs for logic-only CI checks.

---

## 4. Security posture

### 4.1 Current security model

Wiretap is a **local trust-boundary tool**:

| Control | Status |
|---------|--------|
| Secrets in env only | Implemented |
| `.env` chmod 600 | Implemented |
| API never returns secret values | Implemented |
| Suite YAML has no secrets | Implemented |
| Path traversal validation | Implemented |
| Managed secret key allowlist | Implemented |
| AgentGraph strips sensitive tool fields | Implemented |
| Prompt apply hash verification | Implemented |
| HTTP body logging avoided | Implemented |
| UI binds localhost by default | Implemented |
| Vulnerability reporting process | SECURITY.md |

### 4.2 Security gaps (local deployment)

| Gap | Risk | Mitigation |
|-----|------|------------|
| No UI authentication | Anyone on network can access secrets API if `--host 0.0.0.0` | Always bind localhost |
| Flat `.env` file | Key compromise exposes all secrets | Use OS keychain or secret manager for high-security environments |
| Call recordings on disk | PII in WAV/JSONL files | Encrypt disk; set retention policy; restrict file permissions |
| No request rate limiting on API | DoS on local server | Bind localhost; don't expose publicly |
| MCP has full simulate access | Agent can trigger expensive dials | Use in trusted dev environments only |

### 4.3 Data sensitivity

Simulation artifacts may contain:

- Full call transcripts (customer-like test dialogue)
- WAV audio recordings
- Tool call arguments (may include PII depending on agent)
- Judge reasoning and scores

Treat `~/.wiretap/simulations/` as **sensitive data**. Apply retention policies and access controls appropriate to your compliance requirements.

---

## 5. Observability

### 5.1 Current signals

| Signal | Implementation | Production-grade? |
|--------|----------------|-------------------|
| CLI progress | Rich live boards | Adequate for local use |
| Batch progress | SSE events + disk sidecars | Adequate for local UI |
| Artifacts | JSONL + WAV per call | Good audit trail |
| Health check | `GET /api/health` | Basic |
| Logging | Minimal structured logging | Insufficient for ops |
| Metrics | Per-artifact `metrics` dict | No aggregation |
| Tracing | None | Not implemented |
| Alerting | None | Not implemented |

### 5.2 Audit trail

Every simulation produces a `SimulationArtifact` with:

- Full turn-by-turn transcript with timing
- Judge score, verdict, and reasoning
- Deterministic rule results
- Tool call evidence (when available)
- WAV audio file path
- Regression flag vs baseline
- Metrics (turn count, duration, tool counts)

This provides a complete record for post-hoc review but no real-time aggregation.

### 5.3 Recommended observability for CI

```bash
# Structured output for log aggregation
wiretap report --json > report.json

# Archive artifacts
tar czf wiretap-artifacts.tar.gz ~/.wiretap/simulations/ ~/.wiretap/evaluations/

# Upload as CI artifacts for debugging failed runs
```

---

## 6. Hosted service hardening (not current scope)

If Wiretap were deployed as a hosted multi-tenant service, the following would be required. **None of this is implemented today.**

### 6.1 Authentication and authorization

- [ ] User authentication (OAuth, API keys)
- [ ] Tenant isolation for suites, artifacts, and secrets
- [ ] Role-based access (admin, viewer, runner)
- [ ] API rate limiting per tenant

### 6.2 Secret management

- [ ] Vault / KMS integration (replace flat `.env`)
- [ ] Per-tenant secret scoping
- [ ] Secret rotation support
- [ ] Audit log for secret access

### 6.3 Persistence and scaling

- [ ] Database for artifacts, suites, and evaluations (replace JSONL)
- [ ] Indexed search across simulation history
- [ ] Persistent job queue for long-running batches (replace in-memory state)
- [ ] Horizontal scaling with shared state store
- [ ] Artifact retention and archival policies

### 6.4 Infrastructure

- [ ] Docker container image
- [ ] Kubernetes manifests with health/readiness probes
- [ ] Auto-scaling based on batch queue depth
- [ ] TLS termination
- [ ] Backup and disaster recovery

### 6.5 Observability (production-grade)

- [ ] Structured JSON logging
- [ ] Prometheus metrics export
- [ ] OpenTelemetry tracing
- [ ] SLO dashboards and alerting
- [ ] Error tracking (Sentry or equivalent)

### 6.6 Compliance

- [ ] Call recording consent management
- [ ] Data encryption at rest and in transit
- [ ] GDPR/CCPA data deletion workflows
- [ ] SOC 2 controls

---

## 7. Testing readiness

### 7.1 Current test coverage

| Area | Tests | CI in repo? |
|------|-------|-------------|
| Transports | Factory, turn gate, Vapi, Retell, LiveKit, PSTN, SIP | No |
| Evaluation | Judge bands, rules, meta-check, concurrency, advisor | No |
| Services | Secrets, batches, Twilio, prompt apply | No |
| Importers | AgentGraph IR, remote agents, platform imports | No |
| MCP | Tool contracts, path validation | No |
| CLI | Init, simulate display, PSTN flow | No |
| UI API | FastAPI smoke tests | No |

~380 test functions across ~65 files. Run locally:

```bash
uv run pytest
uv run ruff check src tests
cd ui && npm run lint
```

### 7.2 Testing gaps

| Gap | Impact | Priority |
|-----|--------|----------|
| No in-repo CI pipeline | Regressions caught only if contributors run tests locally | High |
| No live integration tests | Platform adapter breakage found only in manual testing | Medium |
| No frontend E2E tests | UI regressions caught only manually | Medium |
| No load/performance tests | Concurrent dial limits unknown under stress | Low |
| No chaos/fault injection tests | Retry behavior validated only by unit tests | Low |

---

## 8. Operational checklist

### 8.1 Before first production-like run

- [ ] Python ≥ 3.11 installed
- [ ] `uv sync` completed successfully
- [ ] API keys configured in `~/.wiretap/.env`
- [ ] `wiretap status` shows all required keys present
- [ ] Agent is deployed and reachable on target platform
- [ ] Test suite imported or created
- [ ] Concurrency set appropriately (start with 1–2)
- [ ] Disk space available for audio artifacts

### 8.2 Before CI integration

- [ ] Suites exported to git repository
- [ ] CI secrets configured (LLM, speech, platform keys)
- [ ] Pipeline timeout set (voice runs can take 10–30 min)
- [ ] Text transport smoke test passing
- [ ] Live voice dial test scheduled (nightly recommended)
- [ ] Artifact archival configured
- [ ] Pass/fail gate defined (`wiretap report --json`)
- [ ] Cost budget established for API usage

### 8.3 Ongoing operations

- [ ] Review failed scenarios weekly
- [ ] Review inconclusive results separately (infra issues)
- [ ] Rotate API keys periodically
- [ ] Clean up old simulation artifacts (disk management)
- [ ] Update Wiretap when new releases ship
- [ ] Re-import agent config after platform changes
- [ ] Monitor API provider quota usage

---

## 9. Dependency management

### 9.1 External service dependencies

| Service | Required? | Failure impact |
|---------|-----------|----------------|
| LiteLLM provider (OpenAI, etc.) | Yes | Simulator + judge unavailable |
| STT/TTS provider (PyAI, etc.) | Yes (voice) | Voice tests → inconclusive |
| Platform API (Retell, Vapi, etc.) | Yes (live dial) | Cannot connect to agent |
| Twilio | Optional (PSTN only) | Phone tests unavailable |
| LiveKit | Bundled (Retell/LiveKit transport) | Retell/LiveKit dials fail |

### 9.2 No infrastructure dependencies

Wiretap has **no dependency** on:

- Databases (Postgres, Redis, etc.)
- Message queues (SQS, RabbitMQ, etc.)
- Object storage (S3, GCS, etc.)
- Container orchestration (Docker, K8s, etc.)

This simplifies local deployment but limits scalability.

### 9.3 Python optional extras

| Extra | Purpose | Install |
|-------|---------|---------|
| `pstn` | Twilio phone dialing | `uv sync --extra pstn` |
| `mcp` | MCP server for coding agents | `uv sync --extra mcp` |
| `dev` | pytest, ruff, respx | `uv sync --extra dev` |

---

## 10. Version and compatibility

| Component | Version | Notes |
|-----------|---------|-------|
| Python | ≥ 3.11 | Required |
| Python 3.13 | Supported | PSTN extra needs `audioop-lts` |
| Node.js | ≥ 18 | UI build only |
| Package version | 0.1.0 | Pre-1.0; API may change |

No long-lived release branches. Report security issues against latest `main` (see [SECURITY.md](../SECURITY.md)).

---

## 11. Summary

| Question | Answer |
|----------|--------|
| Can I use Wiretap for daily dev QA? | **Yes** — this is the primary use case |
| Can I run Wiretap in CI? | **Yes** — bring your own pipeline and secrets |
| Can I share the UI with my team? | **Not safely** — no auth; localhost only |
| Can I deploy Wiretap as a hosted service? | **No** — significant hardening needed (§6) |
| Is Wiretap production monitoring? | **No** — point-in-time QA, not live ops |
| Where do results live? | `~/.wiretap/` on the machine that ran the test |
| What does a failed CI run mean? | Agent regression (fail) or infra issue (inconclusive) — check both |

Wiretap is **production-ready as a local developer QA tool** with thoughtful resilience for voice testing. It is **not production-ready as a hosted multi-tenant service** without the hardening described in §6.
