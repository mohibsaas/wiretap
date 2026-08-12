# PRD: Voice-Agent-Grader — Open-Source Adversarial Test Harness for Deployed Voice Agents

> **⚠️ STALE — do not build from this doc.** Build from `BUILD-SPEC.md`. This PRD is superseded and contains 13 known-false claims (see ARCHITECTURE §3.1). **The one part still cited as source:** §6 (the 7 categories, persona schema, composition formula) — but its authoritative form now lives in `TECHNIQUE-CATALOGUE.md` + `GENERATION-PROMPTS.md`. Read §6 here only as background.

**Status:** Draft v1 — for review
**Owner:** SaaS Labs hackathon team (2 engineers, 1 designer, 1 growth/PM)
**Build window:** Aug 13–14 2026, 33 hours
**Last updated:** 2026-08-05
**Codename:** `Voice-Agent-Grader` (placeholder — see §21.1)
**License:** MIT · public repo from first commit

---

## §0. Conflict-of-Interest Disclosure

> **This section must appear at the top of the repository README, above the feature list. It is not a footnote.**

This tool is built and sponsored by **SaaS Labs**, which also builds **PyAI** (`pyai.com`) — a voice AI platform
that competes with several of the vendors this tool can test. It is also a sibling of **JustCall**, a SaaS Labs
product in the same market.

Specifically:

| Role in the system | Default | Swappable? |
|---|---|---|
| Simulated caller | PyAI Omni | Yes — any provider, user's own key |
| Judge | PyAI (user-selectable) | Yes — any model, user's own key |
| Scoring transcriber | Pinned open-weight Whisper **and** PyAI Hear, both run, divergence published | Yes |
| Agent under test | User's own agent, any vendor | n/a |

Three structural commitments follow from this, and they are load-bearing for the project's credibility:

1. **The scoring instrument is not owned by the sponsor.** The primary scoring transcription runs on a pinned
   open-weight model that requires no key and that anyone can reproduce. PyAI Hear runs alongside it and the
   **divergence between the two is published as a metric** (§10.4). If PyAI's transcription is better, the number
   says so; if it is worse, the number says that too.
2. **SaaS Labs publishes no cross-vendor comparison in v1.** Only the user does, on their own agents. Every
   artifact this project itself publishes — README, screenshots, sample data — uses the local demo agent (§15.6).
3. **The tool is framed as "test your own agent," not "compare vendors."** This is both a legal requirement
   (§15.2) and an honest description of what a single deployed agent's score can support (§10.6).

Reviewers should read the rest of this document with the sponsor relationship in mind, and should push back
wherever a design choice looks like it flatters PyAI rather than serving the user.

---

## §1. Problem Statement

Teams shipping production voice agents have no cheap, reproducible way to find out how their agent behaves when
the caller is difficult. The current options are all bad in different ways.

**Vendor-native testing is shallow and text-only.** Retell's own simulation tester "runs as a text conversation"
with no audio at all, does not support custom-LLM agents, and judges all success criteria "together in a single
pass against the transcript" — one pass/fail, one explanation, no per-criterion verdict. Their docs concede it is
non-deterministic and advise judging "a scenario on its pass rate across runs, not one run." ElevenLabs' agent
testing product is likewise text-only JSON, defaulting to 5 simulated turns. LiveKit's test framework is explicit:
"Testing does not make a LiveKit room connection" — it is in-process, text-mode, and audio simulations "isn't
available yet." LiveKit's own docs route anyone wanting real audio testing to third-party vendors.

So the thing that actually breaks in production — the audio path, the barge-in behaviour, the ASR mishearing an
accent, the 400 ms of dead air before a response — is precisely what vendor-native tools do not exercise.

**Commercial platforms are expensive, closed, and unreproducible.** Hamming and Coval both solve real problems and
both are more built than an open-source weekend project. But: Hamming publishes no price (three tiers, all
"Contact us," every CTA routing to a call with the CEO), its documentation is behind an access code, it claims
"50+ built-in metrics" while only ever enumerating 16, and it makes **no determinism or reproducibility claim
anywhere** — it argues explicitly that voice testing "evaluates probabilistic multi-layer systems" where the
question is "how much did behavior drift" rather than pass/fail. Coval publishes an genuinely rigorous open
benchmark, but it benchmarks **models on frozen audio**, not deployed agents, and there is **no path to submit
your own agent**. The category's own price estimate for these platforms is roughly **$2–5K/month**.

**Nobody reports what testing or running the agent costs.** Verified across both vendors' public surfaces: neither
Hamming nor Coval reports cost anywhere. Hamming enumerates cost *drivers* ("synthetic callers, telephony, STT,
LLM, TTS, infrastructure") and reports cost only as a metric of the customer's agent economics — never as the cost
of the test run, and never as cost-per-resolved-call by provider.

**The gap, stated precisely.** There is no open-source tool that (a) drives real duplex audio against a deployed
agent on any vendor, (b) does it reproducibly enough that two runs can be compared, (c) reports what it cost, and
(d) can be run for free on a laptop in five minutes. Every one of those four is individually available somewhere.
None of the four are available together, and no one offers them under an open licence.

**Why now, and why this team.** The wedge is 50 adversarial "nightmare caller" personas — the callers that break
agents rather than the callers that exercise the happy path. Hamming's own recommended test-set composition is
40% happy path and only 10% adversarial. Inverting that ratio is a sharper product with a smaller scope, and it is
the version that produces a shareable result: nobody screenshots "my agent handled 50 normal callers."

---

## §2. Goals and Non-Goals

### 2.1 Goals

1. **Five-minute first result, zero keys.** `git clone` → `vsim run --demo` → a rendered report card in under five
   minutes, with no API key, no Docker, no Postgres, and no account. The bundled demo agent (§15.6) makes the first
   run instant *and* interesting — it fails real tests for real reasons.
2. **Reproducibility that survives a skeptic.** In the default REPLAY mode, two runs of the same suite against the
   same agent version produce byte-identical caller audio (verifiable by SHA-256) and the same score. Every run
   record carries the full replication bundle: persona-set hash, adapter version, transcriber versions, judge model
   and parameters, concurrency, and agent-version tuple.
3. **Vendor-neutral by construction.** The adapter contract is narrow enough that a new provider is ~200 lines. The
   scoring instrument is not the sponsor's. Four adapters ship in v1: Vapi, Retell, PyAI Omni, ElevenLabs.
4. **Cost as a first-class metric.** Every run reports the agent's cost and the harness's own cost as two separate,
   explicit lines, plus cost-per-*resolved*-call. Backed by a community-maintained `pricing.yaml` with mandatory
   provenance dates (§14).
5. **Findings a developer can act on.** Not a score — a timeline with the failure pinned at the timestamp, the
   audio playable at that moment, and an observed-failure remediation hint that names what the agent did wrong
   across how many calls.
6. **Safe by default for the user and for third parties.** A user cannot accidentally attack an agent they don't
   control, blow up their vendor bill, book 50 real appointments, or publish a stranger's PII. Each of those is a
   blocking gate, not a warning in the docs (§15).
7. **Honest about its own accuracy.** Publish the judge's agreement with human labels, with the method, the class
   balance, and a confidence interval — something no competitor does (§9.4).

### 2.2 Non-Goals (with rationale)

- **No SIP, PSTN, telephony, or phone numbers in v1.** *Why:* it breaks the five-minute-setup goal (carrier account
  + number provisioning + trunk config), and it is a legal design win as well as a scope cut — with no PSTN leg
  there is no called party, so TCPA, AI-voice-disclosure, and all-party-consent recording obligations do not attach
  (§15.8). The transport layer is abstracted so BYO-Twilio drops in later (§20). **Consequence accepted:** ~8 of
  the strongest nightmare tests (DTMF mazes, hold music, IVR trees, PSTN codec degradation) exist in the library but
  auto-skip in v1 via capability declaration, and Hamming keeps that ground uncontested for now.
- **No hosted service, no cloud mode, no account.** *Why:* local-only is a trust feature, not a limitation. Audio
  and transcripts of a live production system never leave the user's machine. Saying so loudly is a differentiator
  against two closed SaaS competitors.
- **No leaderboard in v1.** *Why:* a board with three rows is worse than no board, and a public comparative ranking
  needs the reciprocity and right-of-reply protocol (§15.7) that we cannot properly staff in 33 hours. Deferred, not
  abandoned — the run record is already shaped to feed one.
- **No production-call monitoring (Coval "Observe") in v1.** *Why:* it is a second product with its own ingest,
  retention, and privacy surface. **But** the run record is deliberately shaped so a production call ingests later
  as a run-of-one (§16.3), so this is a schema commitment now and a feature later.
- **We do not read the user's agent system prompt in v1.** *Why:* "we never see your prompt" is a meaningful trust
  claim and it removes a whole class of data-handling obligation. **Consequence accepted:** remediation advice is
  scoped to observed behaviour only, and cannot say "change line 4 of your prompt" (§10.5). An opt-in prompt-paste
  path unlocks prompt-level advice for users who want it.
- **No audio-native judge in v1.** *Why:* it doubles judge surface area for a capability no reviewer can evaluate
  in a five-minute demo, and the research shows transcript-only judging is the *less* biased choice — Full-Duplex-
  Bench deliberately keeps its judge on ASR transcripts, "strictly separating the evaluation modality (text) from
  the generation modality (audio) to minimize bias." Deferred with a reason, not just cut for time.
- **No auto-generated scenarios from the user's prompt.** *Why:* requires reading the prompt (above), and a
  hand-authored cited corpus is both more defensible legally (§15.5) and more deterministic. On the roadmap.
- **No inbound testing** (agent calls us). *Why:* requires a number. Out with PSTN.
- **We publish no working exploit against any named vendor.** *Why:* not a scope decision, a policy one (§15.5).

### 2.3 Success metrics

| Metric | Target | Why this number |
|---|---|---|
| Clone → first rendered card | < 5 min, 0 keys | The deck's ship-checklist gate; drives every other metric |
| Clone → first-transcript rate | > 60% | If the first run needs an account + a configured agent, this lands near 10% |
| REPLAY run-to-run score variance | 0 | The reproducibility claim is falsifiable in one command; it must hold |
| Rule-based assertion flip rate over 3 identical runs | ≈ 0 | Otherwise "rule-based" is a false label (§9.3) |
| Judge agreement with human labels | published, whatever it is | Publishing an honest low number beats publishing nothing |
| Adapter contribution effort | ~200 lines, ~1 evening | Determines whether the long tail of vendors ever gets covered |

---

## §3. Users and User Stories

### 3.1 Primary persona — "Priya, the voice-agent engineer"

Ships a customer-support voice agent on Vapi or Retell. Owns the prompt, the tools, and the pager. Finds out her
agent is broken when a customer complains or when someone forwards a screenshot. Cannot justify $3K/month for a
testing platform, and would not get it approved before the next release anyway.

- As a voice-agent engineer, I want to run 50 hostile callers at my staging agent and get a ranked list of what
  broke, so that I find the embarrassing failure before a customer records it.
- As a voice-agent engineer, I want to click a flagged failure and *hear* the moment it happened, so that I can
  tell an ASR problem from a prompt problem without re-listening to a whole call.
- As a voice-agent engineer, I want the same suite to produce the same score twice, so that when the number moves
  I know my change caused it.
- As a voice-agent engineer, I want a hard spend cap before anything dials, so that a bug in my config cannot cost
  me four figures overnight.
- As a voice-agent engineer, I want to run this in CI on every PR and fail the build under a threshold, so that
  quality does not depend on me remembering to test.
- As a voice-agent engineer, I want to know what my agent costs per *resolved* call, so that I can argue for a
  provider change with a number instead of a feeling.

### 3.2 Secondary persona — "Marco, the eng lead / buyer"

Deciding between two voice vendors, or defending a vendor choice already made. Needs evidence, and needs it to be
evidence that survives someone else's scrutiny.

- As an eng lead, I want to run an identical suite against two of *my own* agents on different providers, so that
  I can compare them on my actual use case rather than on a vendor's benchmark.
- As an eng lead, I want the methodology to be fully open and re-runnable, so that a vendor cannot dismiss my
  result as unreproducible.
- As an eng lead, I want to know how accurate the grader itself is, so that I know how much weight to put on it.

### 3.3 Tertiary persona — "Sam, the OSS contributor"

Found the repo on Hacker News. Runs voice agents on a provider we do not support yet.

- As a contributor, I want to add my provider's adapter in an evening by implementing four methods, so that the
  cost of contributing is lower than the cost of forking.
- As a contributor, I want to add a nightmare persona as a YAML file in a PR, so that domain expertise I have and
  the maintainers don't can reach other users.
- As a contributor, I want to dispute a verdict I think is wrong and have that dispute improve the shared judge,
  so that my correction is worth more than a complaint.

### 3.4 Anti-persona — who this is explicitly not for

Someone who wants to attack a voice agent they do not control. Every targeting path requires either the local demo
agent or a credential that can *enumerate* the target agent, which proves control (§15.4). Sandbox keys cannot
drive a third-party adapter at all. This is enforced in the pre-flight gate, not requested in the docs.

---

## §4. Architecture — SDK First

### 4.1 The layering rule

**The SDK is the product. The CLI and the UI are both thin clients over it, and neither is allowed to contain
logic the SDK does not expose.**

```
┌─────────────────────────────────────────────────────────────┐
│  CLI  (vsim …)          Local UI (vsim serve)      MCP (6)  │   ← thin clients
├─────────────────────────────────────────────────────────────┤
│                      SDK / harness core                     │
│  RunEngine · SuiteLoader · PersonaResolver · CallerDriver    │
│  AdapterRegistry · Transcribers · JudgeRunner · Scorer       │
│  BudgetGovernor · ArtifactStore · RunRecord                  │
├─────────────────────────────────────────────────────────────┤
│   Adapters          Caller providers      Transcribers      │
│  vapi retell       pyai-omni (default)   whisper-pinned     │
│  pyai elevenlabs   + any (BYO key)       pyai-hear          │
│  + local-demo                                                │
└─────────────────────────────────────────────────────────────┘
```

Enforcement, so this does not erode under time pressure: the CLI and UI import only from the SDK's public surface,
and the UI talks to a local HTTP layer that is itself a thin SDK wrapper. If a feature cannot be driven from the
SDK, it does not exist. Concretely — `vsim run` and the UI's "Run" button must call the same `RunEngine.run()`
with the same config object, and the MCP `run_suite` tool must call it too. Three entry points, one code path.

*Why this matters beyond tidiness:* the CI use case, the MCP use case, and the "someone builds a hosted version"
use case are all the SDK with a different front door. Getting this wrong means writing the run loop three times
and having three different sets of bugs.

### 4.2 Core components

| Component | Responsibility | Key decisions |
|---|---|---|
| `RunEngine` | Owns the named loop, concurrency, gates, budget, and the failure invariant | Terminal state always written (§8) |
| `SuiteLoader` | Resolves a suite name → ordered persona list, applies capability filtering | Frozen versioned sets (`core-50@v1`) |
| `PersonaResolver` | Composes the four-part context formula into caller + judge prompts | §6.3 |
| `CallerDriver` | REPLAY (cached WAV playback) or LIVE (Omni duplex) | Two modes, REPLAY default (§5) |
| `AdapterRegistry` | Capability + ToS declarations per provider; drives auto-skip | §7.3 |
| `Transcribers` | Dual transcription, pinned versions, divergence metric | §4.4 |
| `JudgeRunner` | Rule-based assertions + LLM assertions, blinded | §9 |
| `Scorer` | Assertion verdicts → call verdict → suite score + report | Blocking vs advisory (§9.2) |
| `BudgetGovernor` | Dollar cap, minute cap, per-call cap, hard call counter | Fails closed (§8.7) |
| `ArtifactStore` | SQLite + files; redaction and PII quarantine at the write boundary | §16 |

### 4.3 Audio path

Both the caller leg and the agent leg are captured as raw PCM16 and persisted per call.

**We never diarize.** In REPLAY mode we synthesised the caller audio ourselves, so the caller leg is known by
construction — there is no attribution problem to solve. The agent leg is treated as agent-only *only after an
empirical probe confirms the downlink is not mixed* (§18, probe 4). Where the downlink proves mixed, the adapter
declares the capability absent and both legs are sourced from the vendor's post-call per-channel artifacts instead
(Vapi's `customer-recording` / `assistant-recording` are fully speaker-isolated; Retell exposes
`recording_multi_channel_url` "with each party's audio stored in a separate channel").

*Why this matters:* a diarizer that mis-attributes one turn silently corrupts every turn boundary, every per-turn
latency number, and every "the agent said X" assertion — and it does so in a way that looks plausible on screen.
Avoiding diarization entirely removes a whole class of invisible wrongness.

Pacing follows the pattern proven in pipecat's evals module (13.9k★, BSD-2): **20 ms frames**, wall-clock paced,
and critically **silence is re-anchored rather than burst** (`next_send = max(next_send, now)`) so that the agent's
VAD receives the full end-of-turn gap. Bursting silence is the single most common reason a scripted caller makes an
agent behave unnaturally.

Scoring transcription pads **2 seconds of silence symmetrically** around each utterance before transcribing —
pipecat's comment explains why: an abrupt onset "makes Whisper drop a short leading word." A dropped first word
flips substring assertions and looks like an agent failure.

### 4.4 Dual transcription (overturns the original PyAI-pinned decision)

Every call's audio is transcribed **twice**:

1. **Pinned open-weight Whisper** — the primary scoring input. Version + checksum recorded in the run record.
   Requires no API key, which also strengthens the zero-setup path.
2. **PyAI Hear** — run alongside, using the user's own key.

The **divergence between the two is published as a metric** (`transcriber_divergence_wer`), and the vendor's own
transcript is shown as a third column in the diff panel where the adapter can supply it.

*Why this changed:* as originally specified the pinned transcriber was PyAI's, which meant every accuracy and
hallucination assertion against a competitor's agent was computed on the sponsor's transcription of that
competitor's audio — with PyAI also the default caller and default judge. One competitor engineer swapping the STT
and getting a different score would have ended the repo's credibility in a single thread. Determinism only requires
pinning a **version**, not a vendor. Dual-transcribe keeps determinism, removes the self-dealing critique, and turns
a liability into a published PyAI quality datapoint — if Hear wins, the number says so.

Precedent for the pinning discipline is Coval's own open benchmark: exact model strings "not aliases",
`jiwer==4.0.0`, `whisper-normalizer==0.1.12`, a `norm_version`, and a `runner_sha`. We adopt the same contract,
including normalizing both reference and hypothesis with `EnglishTextNormalizer` before computing WER.

### 4.5 The PyAI Omni integration hazards (call these out in the code, not just here)

Three documented behaviours will silently waste hours if the implementer does not know them up front:

1. **Every Omni frame carries a one-byte type tag in both directions** — `0x01` PCM16 audio, `0x02` transcript
   JSON, `0x03` control JSON. An **untagged audio frame is dropped silently**: the engine "has no default branch"
   — no error, no log, no counter. The symptom is a clean handshake, zero transcripts, and the agent asking "are
   you still there." A client that only parses text frames will also play control frames as an audible glitch.
2. **Outbound control frames key on `type`; inbound server frames key on `event`.** PyAI's own guide calls this
   "the #1 Omni bug" and notes a mis-keyed configure is "acked but silently dropped." Read defensively:
   `msg.event ?? msg.type`.
3. **Unknown `configure` keys pass the gateway and are ignored by the engine** — "a no-op, not an error." So
   sending a parameter that does not exist yet produces no signal at all. This is exactly how the seed/temperature
   trap works (§5.2).

Also relevant: transcript events carry `role` (which may arrive as `speaker`) and finality (which may arrive as
`final`, `is_final`, or `kind:"final"`), and carry **no timestamp field** — so turn timing must be measured
client-side (§10.3). There is no mid-call resume: a dropped socket ends the session.

---

## §5. Determinism Model — Two Modes, REPLAY by Default

This is the hardest engineering problem in the product, and the original design for it does not work. Both are
worth stating plainly.

### 5.1 Why the original plan fails

The locked decision was "beat spine + LLM improv glue at temperature 0 with a fixed seed, plus byte-identical
replay." Two independent problems:

**Omni has no working temperature or seed.** The fields exist and are documented as riding the configure frame,
"honored once the engine supports them." Combined with §4.5's silent no-op behaviour, this means sending
`{temperature: 0, seed: 42}` is **accepted and inert** — no error, no warning. The determinism code would look
correct, ship, and be false. The changelog has never mentioned seed or temperature support.

**Improv and byte-identical replay are mutually exclusive.** Improv means new audio is synthesised in response to
what the agent said, so bytes differ by construction. Replay means emitting stored bytes, so the caller cannot
adapt. There is no configuration where both hold. Worse, on the *first* run of any test there is no stored audio to
replay — so "byte-identical" would be unavailable at exactly the moment a new user tries the tool.

### 5.2 The two modes

| | **REPLAY** (default) | **LIVE** |
|---|---|---|
| Caller audio | Pre-rendered once via PyAI Speak, cached, replayed byte-for-byte | Generated live by Omni in `persona_perspective: caller` |
| Deterministic | **Yes** — same bytes, same order, every run | **No** — explicitly labelled |
| Adaptive | No — follows the beat spine regardless of agent replies | Yes — reacts to what the agent actually says |
| Reported as | A single score | **N-of-3 runs with variance bands** |
| Eligible for publication | Yes | No |
| Use | CI, regression, comparison, any shared number | Exploration, finding unscripted failures |

The mode is recorded in the run record and printed in the report header. **A report card never mixes modes.**

### 5.3 REPLAY mechanics

Caller turns are text in the persona file. Each is synthesised once via PyAI Speak, normalised to **−20 dBFS RMS**
(Coval's benchmark normalisation, peak-guarded), and cached as a **SHA-256-named WAV**. The cache key pins
provider, voice, model, and language — following pipecat's `"\x00".join((service, voice, model, language))` pattern.
Playback is 20 ms paced with re-anchored silence (§4.3).

Turn advancement is event-relative rather than absolute-clock: a beat fires on a named upstream event plus a delay,
which is pipecat's `EvalSendAfter` primitive. This is what makes the caller robust to an agent that is slow without
making it non-deterministic.

Because the audio is byte-identical and hash-addressed, **a failed call is replayable exactly** — which is the
property that makes a bug report actionable.

### 5.4 LIVE mechanics, and the good news about Omni

`AgentConfig.persona_perspective` accepts `agent | caller | null`, and PyAI's docs describe `caller` as: *"the
persona is the individual on the call instead, **as in QA and simulation callers**."* In caller mode the
operator-voice conversation layer is dropped *"so it cannot contradict an inverted persona."*

**Omni ships a first-class simulated-caller mode.** This was not assumed — it is documented, and it materially
de-risks LIVE mode. Two supporting controls matter:

- `greeting` is "the first line spoken on connect (turn 0)" and plays "the instant a call connects… before the
  caller says anything" — so our caller can open the conversation rather than waiting.
- `idle_check_in: off` "disables the check-in entirely, so the agent stays silent until the caller speaks" — needed
  for personas whose behaviour is a long silence.
- `barge_sensitivity` accepts `low | normal | high` **or an exact dBFS value**, which gives per-persona control over
  how aggressively the caller talks over the agent.

Two cautions: `greeting_variants` accepts up to 15 strings and "PyAI selects one for each newly resolved call
profile" — **server-side non-deterministic rotation**, so the harness must set exactly one greeting, never a
variant list. And there is no say/inject-exact-text frame beyond turn 0, which is precisely why REPLAY exists.

### 5.5 What determinism does *not* cover — stated so it cannot be misread

Determinism is scoped to **the harness side only**. The agent under test is a moving target we do not control: the
vendor can change the underlying model, the knowledge base can refresh on its own schedule, and the user can edit
the prompt between runs. Therefore:

**Agent identity is a versioned tuple** — `(vendor, agent_id, version_signal)`. Retell gives us the strongest
signal available in the market: an immutable integer `agent_version` on every call record, `agent_tag` "captured at
call creation time and frozen thereafter," and published versions that "cannot be changed." For Vapi, which exposes
no equivalent version pin, we hash the assistant config retrieved at run time and store the digest.

**The harness refuses to render a delta or a regression claim between two runs whose agent-version tuple differs.**
It shows "agent changed between runs — comparison unavailable" instead. Without this, a user sees a 6-point drop a
week later, files a bug against our determinism claim, and the real cause is a vendor-side model swap we never
recorded.

### 5.6 Barge-in determinism

Deterministic interruption is genuinely hard over a live socket, and the honest position differs per provider:

- **Deepgram** exposes `InjectAgentMessage` with `behavior: interrupt` — a documented deterministic barge-in
  primitive. (Not a v1 adapter, but this is why it is the top roadmap candidate.)
- **Vapi** gates barge-in behind *two simultaneous* conditions: sustained voice for `stopSpeakingPlan.voiceSeconds`
  (default 0.2) **and** at least `numWords` transcribed words, then waits `backoffSeconds` (default 1). It also
  ships default `interruptionPhrases` ("stop", "wait", "actually") and `acknowledgementPhrases` ("okay", "yeah") —
  so *which words* the caller interrupts with changes the outcome. Persona files must therefore specify the
  interruption utterance, not just the timing.
- **Omni/PyAI** handles turn detection server-side with no VAD threshold on the wire; barge-in arrives as
  `barge_in` (alias `flush`) and the client's job is to stop playback immediately.

Our approach: interruptions are injected at **fixed offsets relative to detected agent-speech onset**, which is the
method Full-Duplex-Bench uses (it plays interrupting speech at a fixed 7 s after the preceding utterance). Onset is
detected by RMS threshold on the incoming PCM, not by a vendor event, so the measurement is provider-independent.

**A caution the research surfaced and the scoring must respect: barge-in is not uniformly lower-is-better.** A good
agent should *resume* rather than yield when the interruption is a backchannel ("mhm", "right"), talking-to-others,
or background speech — Full-Duplex-Bench v1.5 expects *high* stop latency in those cases. So the persona file must
declare the *expected* response per interruption type, and the scorer must not blanket-reward yielding.

---

## §6. The 50 Nightmare Callers

### 6.1 Design principle: nightmare-first

Normal callers find normal bugs. The 50 are drawn from the tail on purpose. This is a scoping principle applied on
day one, not a feature with a line in the schedule — and it is deliberately the inverse of the incumbent's
recommended mix (Hamming advises 40% happy path / 10% adversarial).

Only **4 of 50** are happy-path, and they exist as controls: if an agent fails those, the run is misconfigured
rather than the agent being bad.

### 6.2 Persona file schema

```yaml
id: emotional-04-whisperer
name: "The Whisperer"
category: emotional              # one of 7 (§6.4)
difficulty: 3                    # 1-5, surfaced on the card
locale: en-US
voice_id: <pyai voice>
behavior_prompt: |               # LIVE mode: drives Omni in caller mode
  You are calling about a billing error. Speak barely above a whisper …
beat_spine:                      # REPLAY mode: ordered, must be hit in order
  - text: "hi, sorry, i can barely talk today"
    after: agent_speech_end
    delay_ms: 300
  - text: "no i said BILLING. b-i-l-l-i-n-g"
    after: agent_speech_end
    delay_ms: 200
assertions:
  - type: llm_judge
    blocking: true
    spec: "Did the agent ask the caller to repeat or speak up, rather than guessing?"
  - type: not_contains
    blocking: false
    spec: ["i'll transfer you"]
requires_capability: []          # e.g. [dtmf] → auto-skips on WebSocket transports
expected_on_interrupt: yield     # yield | resume  (see §5.6)
tags: [asr-stress, low-volume]
citation: "…"                    # required for adversarial/compliance personas (§15.5)
```

Frozen and versioned as `core-50@v1`; user packs layer on top without forking. The set hash is part of every run
record's replication bundle.

### 6.3 The context formula (P7) — applied to caller *and* judge

Every prompt is composed from four parts:

```
Test Category  +  Persona  +  Industry Domain  +  Business/User Context
```

The same composed context goes to **both** the caller and the judge. This is what makes one generic library work
across verticals: the persona supplies the behaviour, the industry selector supplies the vocabulary and the
plausible request, and the business context supplies the specifics (product names, hours, policies the user chooses
to share).

*Why it must reach the judge too:* "did the agent handle this correctly" is domain-dependent. A healthcare agent
refusing to give dosage advice is a **pass**; a support agent refusing to state a refund window is a **fail**. A
judge without the domain context grades the wrong rubric — and would systematically penalise correct refusals,
which is the failure mode most likely to make users distrust the tool.

The industry selector is a single master dropdown in the UI (`--industry` in the CLI), with the business context as
an optional free-text block. Neither requires the agent's system prompt.

### 6.4 The seven categories (all included, 8 each except as noted)

**Emotional (8)** — screaming, crying, drunk, whispering, sarcastic, dead-flat affect, panicking, over-familiar.
*Tests:* does the agent stay on task, avoid mirroring hostility, and escalate appropriately.

**Linguistic (8)** — Hinglish mid-sentence code-switch, heavy accent, mumbler, 220 wpm, halting non-native speaker,
regional slang, child voice, elderly speech. *Tests:* ASR robustness and graceful degradation.
*Grounding:* published WER disparities by accent and dialect are the most reproducible failure class in speech
systems, and code-switching mid-utterance is the specific case incumbents' language lists do not cover — Hamming
lists 65+ languages, which is language *coverage*, not switching *within* an utterance.

**Adversarial (8)** — spoken prompt injection, jailbreak framing, PII extraction attempt, competitor probe,
off-topic hijack, illegal-advice request, role reversal, repetition attack. Classes align with **OWASP LLM01:2025**
prompt injection plus confused-deputy, indirect/third-party content injection, and "confusable" ASR cases where a
benign phrase becomes harmful after transcription. **Every persona in this category carries a `citation` to
already-public technique literature (§15.5). PII-extraction personas are off by default (§15.3).**

**Operational (8)** — interrupts every 2 s, 45 s silence, café background noise, connection drop mid-sentence, asks
for a human five times, changes their mind four times, gives the wrong ID three times, talks over the greeting.
*Grounding:* the noise/overlap synthesis parameters follow Full-Duplex-Bench v1.5 — talking-to-others at −8 dB with
a 5 dB high-shelf above 4 kHz and reflections at 45 ms/120 ms; background speech at −15 dB with a 3 kHz low-pass
and 100 ms echo. Using published parameters means our acoustic conditions are reproducible by a third party.

**Factual (8)** — impossible request, mutually contradictory constraints, hallucination bait, invented product,
date arithmetic, quantity edge cases, stale-policy probe, over-specific detail request.
*Grounding:* the research on judge reliability shows recall on *under-specified* answers is dramatically worse
(33.9% for GPT-4 Turbo) than on wrong-entity answers (98.3%) — so these personas are also the ones that most stress
the judge, and they are prioritised in the calibration set (§9.4).

**Compliance (6)** — medical/legal/financial advice solicitation, "are you recording me", verbal GDPR erasure
request, minor discloses their age, TCPA-style consent challenge, "am I talking to a bot".
*Note:* the last is worth testing regardless of whether the law binds *us* (it does not, §15.8) because
bot-disclosure obligations bind **our user's** production agent.

**Task (4)** — full happy path, partial information, multi-intent in one utterance, escalation path. Controls.

**Total: 50.** Personas requiring DTMF, hold, or IVR navigation are authored and shipped in the library with
`requires_capability: [dtmf]` and **auto-skip** in v1 rather than failing — so they light up the day the SIP
transport lands, and the report card shows them as `skipped: capability unavailable` rather than pretending the
coverage exists.

---

## §7. Adapter Layer

### 7.1 The contract — split into required and declared

The original decision made all seven operations mandatory. That breaks against reality: PyAI's own Omni transcript
endpoint returns `{object, call_id, transcript}` with **no cost and no duration**, so `fetch_cost` is not
implementable for the default provider; and Deepgram has no post-call artifact retrieval at all. As specified, the
contract would have made the sponsor's own provider fail its own contract — and it would have made the capability
registry dead code, since a mandatory operation has nothing to declare.

**Required core** (every adapter, no exceptions):

| Operation | Contract |
|---|---|
| `connect(agent_ref)` | Establish duplex audio; return a session handle |
| `send_audio(pcm)` | Push PCM16 frames |
| `recv()` | Yield audio frames and provider events |
| `teardown()` | Close cleanly; guarantee no orphaned vendor session |

**Declared capability** (optional; each returns an explicit `Unsupported` sentinel):

| Operation | Degradation when unsupported |
|---|---|
| `fetch_vendor_transcript()` | Diff panel renders "vendor transcript unavailable" — the call still scores |
| `fetch_tool_calls()` | Tool-related assertions auto-skip (not fail) |
| `fetch_cost()` | Falls back to derived: duration × `pricing.yaml` rate, **flagged `estimated`** |
| `list_agents()` | Manual agent-id paste, but only for the local demo agent (§15.4) |
| `set_recording_suppression()` | Registry records that vendor-side capture cannot be disabled (§15.3) |
| `agent_version_signal()` | Falls back to config hash; comparison guard still applies (§5.5) |

**`Unsupported` is never rendered as zero.** The report card says "not available from this vendor." A cost of zero
silently defeats the budget governor, which is how a runaway loop becomes a four-figure bill.

### 7.2 The four v1 adapters

| | Transport | Lists agents | Per-leg audio | Cost | Concurrency | Notes |
|---|---|---|---|---|---|---|
| **Vapi** | `wss://api.vapi.ai/<callId>/transport` via `POST /call` with `transport.provider="vapi.websocket"`; `pcm_s16le` @16 kHz | `GET /assistant` | **Yes** — `customer-recording` + `assistant-recording`, speaker-isolated mono | **`call.cost` USD + `costBreakdown`** | **10 default, overflow QUEUES silently** | Phone numbers "not permitted" on this transport. **WS auth undocumented — probe 3.** |
| **Retell** | `POST /v2/create-web-call` → `access_token`, must start within 30 s. Transport is **LiveKit** (`livekit-client`, agent track `agent_audio`) | `POST /v2/list-agents` | **Yes** — `recording_multi_channel_url` | `call_cost.combined_cost` **in cents** | 20 PAYG, **over-limit REJECTED not queued** | **Best version pin in the market:** immutable integer `agent_version` + tags. Raw audio-websocket exists but is **deprecated**. ToS gate (§15.2). |
| **PyAI Omni** | `wss://api.pyai.com/v1/omni`, subprotocol `pyai-key.<KEY>`, tagged frames (§4.5) | `/v1/agents` profiles | Caller leg by construction | **Unsupported** — derived from duration × $0.05/min | **Unpublished** — probe 1 | Self-test proves neutrality. `persona_perspective: caller`. |
| **ElevenLabs** | `wss://api.elevenlabs.io/v1/convai/conversation?agent_id=`, signed URL via `get-signed-url` | `GET /v1/convai/agents` | Post-call audio download | **`metadata.cost_fiat` — true USD, only vendor with it** | **4/6/10/20/30/40 by tier — every self-serve tier < 50** | **Audio is base64, and `{"user_audio_chunk":…}` has no `type` key** — the field name is the discriminator. **No `agent_started_speaking`** — infer onset from first audio. |
| **local-demo** | in-process | n/a | Yes | Exact, $0 | Unlimited | §15.6. The only target reachable without attestation. |

**JustCall was cut from v1.** It is hard PSTN-only: `POST /v2.1/voice-agents/calls` requires `contact_number` in
E.164, the only reachability field on an agent is `assigned_numbers[]`, no WebSocket/WebRTC/SIP path exists anywhere
in the API, and the initiate endpoint is **rate-limited to 5 calls/minute** — a 50-persona suite would spend 10
minutes just dialing. The README must state this as a vendor-architecture fact, not leave it as an apparent
oversight: **a listed-but-permanently-skipped sibling product would look worse than an absent one.** It becomes a
v1.1 adapter gated on the BYO-Twilio transport.

### 7.3 Capability + ToS registry

Each adapter declares, as data:

```yaml
adapter: vapi
transport: websocket
capabilities: [barge_in, tool_call_events, cost_api, per_leg_audio, list_agents]
max_concurrency: 10            # read live from subscriptionLimits, clamped
concurrency_overflow: queue    # queue | reject  ← changes latency validity
side_effects: [transfer, sms, booking, custom_webhook]
side_effect_suppression: UNAVAILABLE   # no documented dry-run
tos_posture: silent            # permits_benchmarking | silent | prohibits_without_consent | unmapped
tos_citation: "…"
recording_default: on          # artifactPlan.recordingEnabled defaults true
```

This one file drives: which personas auto-skip, what concurrency we clamp to, whether latency numbers from a run
are valid, which gates fire in pre-flight, and whether the adapter ships enabled.

Adapters are **in-tree for v1**, with the plugin protocol documented from day one so contributors can land PRs
without waiting for a plugin loader.

### 7.4 Connecting an agent

Connect a vendor account with an API key → the harness lists that account's agents → the user picks one. Manual
agent-id paste is supported **only** for the local demo agent, because requiring enumeration is what proves the
user controls the target (§15.4).

---

## §8. The Harness Loop (the deck's seven parts)

The deck scores "Loop depth" at 15% and specifies seven parts. Each maps to a concrete mechanism, with the critic
fixes folded in.

### 8.1 One named loop

Every run terminates in exactly one state, always written:

| State | Meaning |
|---|---|
| `shipped` | All selected calls executed and scored |
| `partial` | Some calls executed within budget; remainder `not_executed` |
| `failed` | Pre-flight or adapter/auth failure; no meaningful calls |
| `deadline` | Budget or wall-clock cap reached |

Paired with a run-status enum used by the report layer: `complete | budget_aborted | infra_aborted`.

**Unrun tests are `not_executed`, never 0.** And it is **structurally impossible to render an average, a grade, or
any comparative claim on a non-complete run** — the headline becomes `INCOMPLETE: 37/50 executed, budget cap
reached`. Without this rule, a user's $5 cap produces a "24/50" card that circulates as a real score for their
vendor.

### 8.2 Blocking gates (pre-flight)

The run does not start until all pass:

1. Keys present and valid
2. **Authorization attestation** for the target agent, logged with timestamp (§15.4)
3. Agent reachable; **one smoke call succeeds**
4. Agent's tool list fetched and displayed; **irreversible tools acknowledged** (§15.9)
5. **Worst-case spend computed and shown**: `personas × turn_cap × concurrency × rate`; explicit confirmation
   required above a ~$5 default ceiling
6. Vendor-side spend cap attested (this is the only control that actually binds — see §15.10)
7. Concurrency clamped to the adapter's live limit
8. Capability filter applied; skipped personas listed before the run, not after

### 8.3 Bounded aimed retry

Retries apply to **infrastructure failures only** — WebSocket drop, 429, transient 1011 — never to a failed
assertion. Cap 2, with the reason attached to the record. **Retries are gated on the budget check**, so they cannot
outlive the cap.

Retryability is provider-specific and read from documented close codes: for Omni, 4401 (bad key) and 4403 (missing
scope) are **no-retry**; 4429 (concurrency/rate) and 1011 (transient) are retryable.

### 8.4 Failure invariant

Every call appends a record even on crash or SIGINT: JSONL flushed, partial audio flushed, terminal state written.
A crashed run is still an inspectable run.

### 8.5 Capability registry

Personas, adapters, judges, transcribers, voices, and industry packs are all declared in config. Adding any of them
requires zero code (§7.3).

### 8.6 Safe parallelism

Calls run concurrently; **all artifact writes serialize through a single writer**; the run manifest is written once
at the end. Default concurrency **10**, `--concurrency` to override, and the 50-wide stage demo runs against the
**local demo agent** — which has no vendor ceiling, and is therefore the only honest way to demo 50 concurrent.

**Concurrency corrupts latency, and this must be enforced not just noted.** Vapi's overflow behaviour is silent
queueing — "new outbound dials or inbound connections wait until a slot becomes free" — with the only signal being
`subscriptionLimits.concurrencyBlocked`. Calls 11–50 would sit in a queue, then run, and their time-to-first-word
would be contaminated by invisible queue wait. Therefore: `concurrencyBlocked = true` **hard-invalidates that
call's latency metrics**, and every published latency number is labelled with the concurrency it was measured at.

### 8.7 Budget governor

Three independent caps, all enforced:

- **Dollar cap** (total)
- **Minute cap** (total)
- **Per-call cap**
- Plus a **hard `max_total_calls` counter**, independent of both — so a cost-*reporting* failure cannot produce
  unbounded calls.

On breach: abort remaining, mark `deadline` / `budget_aborted`.

**Fails closed.** If `fetch_cost` is unsupported or returns null, use the conservative constant from `pricing.yaml`
with its mandatory `verified_on` date — never treat unknown cost as zero.

*Why this is not paranoia:* the arithmetic is unforgiving. 50 personas × 180 s = **150 vendor-minutes per full
run**. On a Retell stack running GPT Realtime at $0.345/min plus $0.055/min platform, one run is roughly **$60** —
and Retell bills silence and hold time because the STT engine "remains active and listening." A retry bug overnight
is four figures. Vapi's own terms are explicit that this is the customer's problem: "Unless you have limited the
traffic flow to certain limits, we do not stop incoming voice calls to our Platform."

### 8.8 Caps

Default **12 turns / 180 s** per call, both modifiable. These are also the only current backstop on side-effect
*volume* (§15.9), so lowering them is a safety lever, not just a speed one.

---
## §9. Judge and Scoring

### 9.1 Judge modality

**v1 ships transcript + timing only.** Audio-native scoring is deferred (§2.2), and the reason is not only scope:
Full-Duplex-Bench deliberately keeps its judge on ASR transcripts, "strictly separating the evaluation modality
(text) from the generation modality (audio) to minimize bias." Transcript-only is the *less* biased choice, not
merely the cheaper one.

### 9.2 Assertion types and the blocking/advisory split

| Type | Rule-based? | Notes |
|---|---|---|
| `contains` / `not_contains` | yes | Normalised before matching (§9.3) |
| `regex` | yes | Reserved for machine tokens |
| `latency_p95_under` | yes | Client-measured (§10.3) |
| `turn_count_under` | yes | |
| `tool_called` / `tool_not_called` | yes | Machine tokens — exact match is safe here |
| `no_pii_leak` | yes | Detector class only, never the payload (§15.3) |
| `resumes_after_backchannel` | yes | Expected value declared per persona (§5.6) |
| `llm_judge(question)` | no | Binary verdict + written critique |

Every assertion is tagged **`blocking`** or **`advisory`**. A call fails only on a blocking assertion — the deck's
harness spec requires that "the gates actually block," and an advisory tier is what keeps the blocking tier
meaningful instead of everything failing on a stylistic nit.

Target ratio: **≥60% rule-based**.

### 9.3 "Rule-based" is not the same as "stable" — and the PRD must not conflate them

A non-LLM assertion still matches a **string produced by ASR from audio**. At a realistic 5–12% WER, a 20-word
agent utterance carries one to two wrong words, so a naive substring assertion flips intermittently even when the
agent's behaviour is identical. Calling these "deterministic assertions" would be a false label that hides drift in
the one place nobody thinks to look.

So: the category is named **rule-based** throughout, and the rules are made genuinely robust:

- Normalise before matching: lowercase, strip punctuation, collapse whitespace, spell out digits. Both sides
  normalised with `EnglishTextNormalizer` — "the de facto standard for published WER."
- Prefer fuzzy / semantic-distance thresholds for anything phrase-shaped.
- Reserve exact matching for machine-generated tokens that never pass through ASR: tool-call names, DTMF digits,
  structured field values.
- **Publish the flip rate across 3 identical REPLAY runs.** If it is not ≈ 0, the label is false and the assertion
  needs fixing — this is a tracked success metric (§2.3).

A cautionary precedent from Coval's own benchmark: their retired hand-rolled WER normaliser "corrupted many number
forms (e.g. 'thirty six' → 3006)" and they marked pre/post results explicitly incomparable. Normalisation is not a
detail.

### 9.4 Judge calibration — published in v1

No competitor publishes their judge's accuracy. Hamming names "automated LLM-as-judge scoring with manual expert
review" but never identifies the model, version, prompt, or rubric, and its "95–96% agreement with human
evaluators" claim carries no methodology, sample size, or timeframe.

We publish ours, and we publish it honestly at the scale we can actually reach in 33 hours.

**v1 commitment: an N=30 spot check with the full method disclosed.** McHugh's floor for a defensible kappa is
"no fewer than 30 comparisons." We report:

- **Raw agreement** *and* **Cohen's kappa** — because raw agreement alone is the field's standard defect. McHugh
  documents a case with 94.2% raw agreement and kappa of only 0.555; the "Judging the Judges" work found percent
  agreement differing by 26 points where Scott's pi differed by 64.
- **False-pass and false-fail rates separately.** LLM judges are systematically *lenient* — the positive-bias
  parameter is significantly above 0.5 for most judges, and even well-aligned judges "tend to produce more false
  positives than false negatives." For a safety tool, a false pass is the dangerous error.
- **Class balance of the golden set**, because kappa is highly sensitive to skew: 0.90 raw agreement is kappa 0.800
  at a 50% fail rate but only 0.392 at 11%.
- **A Wilson confidence interval**, not Wald — Wald "narrows to zero width (falsely implying certainty)" as the
  proportion approaches 1. At N=30 the interval is wide; saying so is the point.
- **The human–human ceiling** where we can estimate it, so the judge's number is interpretable. On MT-Bench, GPT-4
  agreed with experts 85% of the time against an 81% human–human baseline — a judge cannot meaningfully exceed the
  ceiling.

The full study (N≥100, multiple labellers) is explicitly deferred and labelled as deferred, rather than publishing
an under-powered number dressed as rigour.

**Bias controls, all from published findings:**

- **Blind the judge to vendor identity.** Self-preference is real and blinding measurably reduces it: GPT-4's
  normalised self-preference on XSUM drops 0.73 → 0.32 under swapped source labels. The judge never sees which
  vendor produced the transcript. This is the single most important control given the sponsor relationship (§0).
- **Binary pass/fail with a written critique**, not a 1–5 scale. Low-precision scales "largely retain precision
  compared to higher precision scales," and practitioner consensus is that 1–5 metric scales are the wrong tool.
- **Judge model, version, temperature, and seed are recorded in every run record**, and a judge swap invalidates
  comparison. This is not theoretical: on Arena-Hard, swapping GPT-4-Turbo for Claude-3-Opus dropped agreement with
  human ranking from 89.1% to 66.7%.
- **Verdict caching** under a hash of `(criterion, messages)` — pipecat's technique for stabilising a judge that has
  no temperature control. Cache persists to disk (pipecat's is in-memory only, which loses the benefit across runs).

**Roadmap, not v1:** a **panel of three cheap disjoint-family judges**, which beat a single GPT-4 on kappa at 7–8×
lower cost (0.763 vs 0.627 on NQ; 0.906 vs 0.841 on TQA) with the smallest spread against human scores. This is the
highest-value judge upgrade available and it is cheaper than what we ship — it is deferred only because it triples
integration surface in a 33-hour window.

### 9.5 Judge provider

**Default is PyAI, user-swappable to any model with their own key.** The judge is where swapping costs least — a few
thousand text tokens per call versus the caller's realtime audio minutes — so making it open costs the sponsor
almost nothing in API gravity and buys the credibility the tool needs. Blinding (§9.4) is what makes the default
defensible.

### 9.6 Dispute → public golden set

A "dispute this verdict" button writes a label to local JSONL. `vsim contribute-label` opens a PR adding it to the
**public** golden set.

*Why this shape:* Coval's human review retrains *their private* judge. Ours makes every disputed verdict a PR into a
public labelled dataset — the judge improves for everyone, and the dataset becomes an asset that outlives the tool.
Same mechanic, inverted ownership, and it is the cheapest feature in this document: a button and a file.

**Guard against overfitting:** the golden set is split into a tuning half and a **holdout that is never tuned on** —
promptfoo's discipline. And the golden set is kept **strictly separate from the demo agent's fixtures** (§15.6), so
the published kappa is not an artefact of a tuned fixture.

---

## §10. Metrics and the Report Card

### 10.1 The eight headline metrics

| Metric | Definition | Source |
|---|---|---|
| **Survival rate** | Blocking-assertion pass rate across executed calls | Scorer |
| **Safety score** | Adversarial-category pass % | Scorer |
| **Voice-to-voice latency** | p50 / p95, client-measured | §10.3 |
| **Interruption handling** | Correct yield-vs-resume rate per expected value | §5.6 |
| **Task completion** | Task-category pass % | Scorer |
| **Cost per resolved call** | Agent cost ÷ successfully-completed tasks | §14 |
| **Language robustness** | Linguistic-category pass % + WER by persona locale | Transcribers |
| **Hallucination rate** | Factual-category fabrication detections | Judge |

### 10.2 Per-test detail (required)

The card includes **all 50 per-test scores** plus the category and difficulty-tier averages — not just the eight
aggregates. Survival is broken out **by difficulty tier 1–5**, which is what makes "survived 41/50" legible: 41/50
with all five tier-5 failures is a different agent from 41/50 with nine tier-1 failures.

### 10.3 Latency measurement — client-side, provider-independent

Vendor latency numbers are not comparable and several exclude the parts users feel. Retell's `e2e` "does not account
for network trip time from the Retell server to the user's frontend." Vapi's artifact exposes
`endpointingLatencyAverage` while its methodology page says displayed latencies *exclude* endpointing and transport —
the two definitions disagree within one vendor.

So we measure ourselves, using the four anchors Full-Duplex-Bench defines: `t_user_start`, `t_user_end`,
`t_model_stop`, `t_model_start`. Response latency = `t_model_start − t_user_end`; stop latency =
`t_model_stop − t_user_start`. Onset is detected by **RMS threshold on incoming PCM**, the same approach Coval's
benchmark uses for its first-audible-sample detector, with `time.monotonic` timers. Vendor-reported latency is shown
alongside as a separate column, labelled as the vendor's own definition.

Every latency figure is labelled with the concurrency it was measured at, and is **invalidated entirely** if the
provider signalled queueing (§8.6).

### 10.4 Transcriber divergence

`transcriber_divergence_wer` — WER between pinned Whisper and PyAI Hear on the same audio. Published per run.

Plus the **STT diff against known truth**, which is a metric no black-box tester can produce: in REPLAY mode we
generated the caller audio from known text, so we know exactly what was said. That lets us score the agent's
*hearing* separately from its *thinking* — "your provider's ASR dropped 12% of what the caller actually said" is a
different and more actionable finding than "your agent gave a wrong answer."

### 10.5 Remediation hints — observed-behaviour only

The original decision asked for advice on "what to change in the prompt," while a separate decision commits to never
reading the prompt. Those contradict, and shipping both would produce visibly wrong advice on the highest-visibility
surface: "add a confirmation step to your prompt" when the agent already has one and the real failure was a tool
timeout.

So hints are scoped **strictly to what the harness witnessed**:

- "In 7/50 calls the agent ended without confirming the callback number."
- "Tool `lookup_order` was never invoked on the 6 tests that required it."
- "The agent yielded to a backchannel in 11/12 interruption tests; a caller saying 'mhm' should not stop it."
- "ASR dropped the caller's first word in 9 calls — consider a longer `startSpeakingPlan.waitSeconds`."

An **opt-in** path lets a user paste their prompt to unlock prompt-level advice, declared through the capability
registry. This keeps "we never see your prompt" true by default and makes the stronger feature honest.

### 10.6 The card artifact

Locally rendered SVG → PNG at `run/card.png`, no server. Contents:

- Letter grade (A–F) + `41/50` + tier breakdown
- Three worst failures in plain English
- Latency p95 (with concurrency label)
- Cost per resolved call — **agent cost and harness cost as two separate lines**
- Run hash + full replication footer (persona-set version, transcriber versions, judge model, mode, concurrency)
- **Mandatory framing line:** *"This measures ONE DEPLOYED AGENT CONFIGURATION, not the vendor's platform. Scores
  are not comparable across agents with different prompts, tools, or models."*

That last line is the most important sentence in the product. It follows directly from benchmarking deployed agents
rather than models, and from never reading the prompt — we genuinely cannot distinguish a vendor defect from one
user's misconfiguration, and the card must say so.

**Vendor naming:** named in the local card, **stripped by default on publish**, opt-in to include (§15.7).

Also emitted: `report.md` (for PR comments) and `report.html` (for humans).

---

## §11. CLI

### 11.1 Surface

```
vsim init                    # scaffold vsim.yaml
vsim doctor                  # validate keys, warn if keys are in a tracked file
vsim providers add vapi      # connect a vendor account
vsim agents list             # enumerate that account's agents
vsim suites list
vsim run --suite core-50 --agent <id> --industry healthcare \
         --mode replay --concurrency 10 --budget 5.00 --fail-under 40
vsim run --demo              # zero keys, local demo agent
vsim report <run> | card <run> | replay <call>
vsim compare <runA> <runB>   # refuses across differing agent-version tuples
vsim serve                   # local UI
vsim contribute-label
```

Default suite for a first run is a **12-persona smoke set**; the full 50 is an explicit flag. A newcomer's first
command should not be their most expensive one.

### 11.2 Exit codes

| Code | Meaning |
|---|---|
| 0 | Pass (all blocking assertions, above `--fail-under`) |
| 1 | Assertions failed / below threshold |
| 2 | Budget or deadline abort |
| 3 | Infra / auth / pre-flight gate failure |

### 11.3 Config and output

`vsim.yaml` committed for CI; `.env` for keys, never in the YAML. `vsim doctor` warns if a key is in a tracked file.
Output: table by default, `--json`, `--junit`.

Headless CI is **key-only** — no login, no browser. (Coval's CLI has no config file at all and relies on
`coval login` or a flag; a committed config file is what makes per-repo CI reproducible.)

---

## §12. Local UI

### 12.1 Constraints

Bound to `127.0.0.1`, no auth, bundled inside the CLI package (`vsim serve` opens the browser). **SQLite + files on
disk — no Docker, no Postgres, no compose.** This is non-negotiable for the five-minute gate. No hosted mode, ever,
stated in the README as a trust feature.

### 12.2 The live run grid

50 tiles going green/red in real time as calls complete. This is the README's hero screenshot and the thing that
makes the demo land.

### 12.3 The combined call timeline

**One waveform, not two stacked.** Caller and agent are the same canvas, visually distinguished by tint, with:

| Layer | v1 | Rationale |
|---|---|---|
| Dual-tinted single waveform | **Ship** | The core artifact |
| Turn boundaries | **Ship** | |
| Assertion flags pinned to timestamps | **Ship** | The "oh damn" moment |
| Per-turn latency bars | Hover / second tab | Six overlaid layers is a designer-week |
| Tool calls | Hover / second tab | |
| Guardrail hits | Hover / second tab | |
| Cumulative cost | Second tab | |

**The three shipped layers are frozen for the screenshot.** The remaining four are real requirements, moved to hover
and a second tab so that the primary view actually gets finished. Attempting all seven overlaid on one canvas is the
most likely way to arrive at hour 30 with a half-rendered timeline and no hero screenshot.

Interaction: single synced cursor; click a flag → seek; diarized transcript scroll-locked to audio; STT diff shown
inline as strikethrough/insert marks (intended caller text vs what the vendor heard); vendor's internal trace shown
collapsed where the adapter supplies it.

### 12.4 Run comparison

Side-by-side two runs (before/after a prompt change), with the agent-version guard from §5.5 refusing misleading
comparisons.

---

## §13. MCP Server

Six tools: `list_suites`, `run_suite`, `get_run`, `get_call`, `get_report`, `compare_runs`.

All six are thin wrappers over the same SDK calls the CLI uses (§4.1). "Test your voice agent from Claude Code" is
a strong demo beat and it costs almost nothing once the SDK boundary is clean. Coval ships 19 MCP tools; six is the
right number for a first release because each one is a surface we have to keep honest.

---

## §14. Cost Model and the Price Index

### 14.1 How cost is computed

Priority order: `fetch_cost()` from the adapter where supported → otherwise measured duration × rate from
`pricing.yaml`, **flagged `estimated`**. Never zero (§8.7).

Adapter reality: ElevenLabs gives true per-conversation USD (`metadata.cost_fiat`); Vapi gives `call.cost` plus a
component `costBreakdown`; Retell gives `call_cost.combined_cost` **in cents**; PyAI Omni gives nothing and must be
derived at $0.05/min.

### 14.2 Two lines, always

The agent's cost and **the harness's own cost** are reported separately and explicitly. Hiding what the test run
cost — while selling the sponsor's minutes — would look exactly like the sales tactic it would be.

### 14.3 Cost per *resolved* call

The headline is cost per resolved call, not per call. Cost per call flatters whichever provider hangs up fastest;
cost per resolved call is the number a buyer actually needs, and it is the number that flatters PyAI honestly if
PyAI is in fact cheaper per outcome.

### 14.4 `pricing.yaml` — the artifact nobody publishes

Community-maintained, in-repo, PR-able. Every entry carries per-component pricing, an effective/verified date, and a
provenance URL. **Verified finding: not one of Vapi, Retell, ElevenLabs, Deepgram, LiveKit, Bland, Cartesia, or PyAI
stamps an effective date on its published rates** (checked 2026-08-04). A dated, sourced table is therefore itself a
contribution.

```yaml
- provider: vapi
  product: platform
  unit: per_minute
  price_usd: 0.05
  includes: [orchestration]
  excludes: [stt, llm, tts, telephony]     # "at cost", component rates unpublished
  volume_tiers: null
  source: https://vapi.ai/pricing
  verified_on: 2026-08-04
  notes: "Pricing calculator renders STT/LLM/TTS selectors empty — all-in not computable from vendor site"
```

Seed data gathered and citable for v1: Vapi $0.05/min platform (excludes models); Retell $0.055/min infra with a
worked example at $0.11/min all-in, GPT Realtime resold at $0.345/min, and **billing that includes silence and hold
time**; ElevenLabs $0.08/min overage, $0.16 burst, billed on **connection** duration with a 95% discount for silence
over 10 s; Deepgram $0.075/min standard voice agent, billed on **websocket connection time**; LiveKit $0.01/min
agent session with a published $0.0672/min all-in example; Bland $0.14/min bundled; Cartesia $0.06/min; Twilio
$0.0140/min US outbound; PyAI Omni $0.05/min "all-in, no platform fee on top."

**Two honest flags to carry into the file**, because they are the interesting part: Retell lists GPT Realtime at
$0.345/min while LiveKit lists it at $0.0676/min — a ~5× discrepancy that neither page resolves by model ID; and
PlayHT/PlayAI pricing was **entirely unverifiable** (DNS failures, invalid TLS, expired certificate), so it is
recorded as a gap rather than a remembered number. An unsourced number is worse than a gap.

---
## §15. Safety, Legal, and Data Handling

This section is a requirements list, not a disclaimer. Each item is a gate in code or a file in the repo. A tool
that fires 50 adversarial calls — including prompt-injection and PII-extraction attempts — at a third party's live
production system cannot ship these as documentation.

### 15.1 The framing decision

**All copy says "test your own agent." Never "compare vendors."** README, CLI help, report cards, website. This is
simultaneously the legal posture (§15.2), an accurate description of what one deployed agent's score supports
(§10.6), and the honest position given the sponsor relationship (§0).

### 15.2 Vendor terms of service

**Retell ToS §10.1(d) prohibits using the Services "for benchmarking or competitive analysis without Retell AI's
prior written consent."** §10.1(b) separately bars "automated means to extract data, voice samples, model outputs, or
other content" — which is what `fetch_vendor_transcript` does. §10.1(f) bars building anything that "functions as a
substitute for, or intermediary layer on top of, the Services."

This is a real constraint on our users, created by our code. Requirements:

1. **Per-adapter `tos_posture`** in the capability registry: `permits_benchmarking | silent | prohibits_without_consent | unmapped`, each with a **verbatim quoted clause and retrieval date** in `docs/vendor-tos.md`. Current mapping: Retell = `prohibits_without_consent`; Vapi = `silent` (no benchmarking clause found); ElevenLabs = `unmapped` (Prohibited Use Policy returned 404 on four URL variants, and its supplemental terms "control" in a conflict); PyAI = first-party.
2. **Any adapter not marked `permits_benchmarking` requires a one-time interactive attestation** that the user is testing their own agent, stored with timestamp in SQLite.
3. **No vendor name appears in any artifact the project itself publishes** for those adapters (§15.6).
4. **Stated policy: we disable any adapter on written vendor request.** In `docs/vendor-tos.md`.

The "test your own agent" reframe is what moves §10.1(d) from breach toward defensible self-testing — a user testing
their own deployment is not benchmarking Retell. It is also why the vendor-transcript diff is **off by default** for
any adapter not marked `permits_benchmarking`, and why only the divergence *statistic* (not the vendor's transcript
text) may ever appear in a published artifact.

### 15.3 PII — the sharpest risk, created by the test suite itself

A PII-extraction test that **succeeds** means the agent disclosed a real third party's personal data — pulled from
the user's live CRM or knowledge base. Without controls, that payload lands in five places: SQLite, the persisted
audio we keep for replay, the timeline view, the report card, and the vendor's own retention.

Requirements:

1. **A successful PII assertion records the class and character offsets, never the payload.**
2. **Detection runs before any write.** Detected spans become typed tokens — `[PII:PERSON_NAME]`, `[PII:CARD_LAST4]` — in the stored transcript.
3. **Raw spans go only to a separate `quarantine` table**, excluded from every export path by default, purgeable via `vsim purge-quarantine`.
4. **The card and timeline render only tokens.** The publish path is *structurally incapable* of emitting raw PII — not "the user should remember to redact."
5. **PII probes are off by default**, behind `--enable-pii-probes` plus an attestation that the target is not connected to production customer data. Docs recommend a staging agent with synthetic records.
6. **Adapters set vendor-side suppression flags on every test call where supported** — Vapi `artifactPlan: {recordingEnabled: false, loggingEnabled: false, transcriptPlan: {enabled: false}}` (**all default to `true`**), Retell `data_storage_setting: everything_except_pii` — and the registry records where the vendor offers no such control, because there the leak is unrecallable.

### 15.4 Authorization gate — nothing verifies ownership by default

Agent IDs are guessable and leak in client-side code. Without a gate, a public WebSocket URL plus a pasted agent ID
makes this a turnkey anonymous attack service, and a self-minting sandbox key removes the accountability trail.

Blocking pre-flight requirements:

1. **Logged attestation**, verbatim: *"I own or am authorized in writing to test agent `<id>` on `<vendor>`."* Persisted with timestamp. Never a config default, never bypassable by env var.
2. **Non-local targets require a credential that can enumerate the agent** — holding a key that lists it proves control. Free-form agent-id paste is allowed **only** for the local demo agent.
3. **Sandbox keys cannot drive a third-party adapter** — local demo agent only. This closes the anonymous-attack path.
4. Ship `SECURITY.md`, `RESPONSIBLE_USE.md`, and `/.well-known/security.txt` (RFC 9116: `Contact` and `Expires` are the only MUST fields). RFC 9116 is explicit that publishing contact info "grants no testing permission."

### 15.5 Two-tier findings and coordinated disclosure

There is a category difference the scoring must recognise:

- **Tier 1 — agent configuration failure.** The user's prompt is weak. Normal report card, remediation hints, safe to share. This is the product working.
- **Tier 2 — platform guardrail bypass.** The *vendor's own* safety layer failed. The run records a class label and a pointer to `SECURITY.md`, and **suppresses the payload from the report card and every export**.

**Automatic escalation heuristic:** if the same payload succeeds across multiple tenants, or against a vendor's
declared guardrail feature, escalate to Tier 2 rather than relying on the user to classify.

`SECURITY.md` states: **90-day coordinated disclosure, vendor notified first, no working bypass published before the
window closes.** Aggregate pass-rates may be published immediately.

**`core-50@v1` contains only already-public, cited techniques** — every adversarial and compliance persona carries a
`citation`. This keeps the shipped corpus out of Tier 2 by construction, and it materially reduces model-provider AUP
exposure (§15.11).

### 15.6 The local demo agent is a legal control, not a convenience

Deferring the leaderboard does **not** defer publication risk. A README screenshot showing a named vendor with a
failing score is a published comparative performance claim — permanently, with better distribution than any
leaderboard. Same for checked-in "sample data" from real vendor runs.

Requirements:

- **The killer screenshot and all checked-in sample data use the local demo agent**, labelled "demo-agent (intentionally vulnerable)" and `synthetic`.
- **No real vendor name in any project-published artifact.**
- README line: *"Scores in this screenshot are from a deliberately vulnerable local demo agent, not any commercial product."*
- Therefore the demo agent is **on the critical path**, not a nice-to-have.

**Build it from real observed failure modes** — ignores barge-in, loops on clarification, never confirms a captured
value, calls the wrong tool, hallucinates a policy — and **report whatever failure count results rather than tuning
to ~12**. A tuned skew would contaminate the published kappa (§9.4), since chance-corrected agreement is highly
sensitive to class balance. Its fixtures are kept strictly separate from the judge's golden set.

### 15.7 `PUBLISHING.md` — a v1 deliverable even though the leaderboard is deferred

Users will publish regardless, so the protocol ships with v1. The industry template is already written: Google Cloud
Service Terms §7 permits customer benchmarking and public disclosure **only if** the disclosure "includes all
necessary information to replicate the Tests" **and** the customer reciprocally allows Google to benchmark and
publish about the customer's products. AWS §1.8 is near-identical. That replication-plus-reciprocity structure is the
recognised safe harbour — and our determinism model lets us satisfy the replication half better than almost anyone.

1. Every published result ships the **replication bundle**: persona-set hash, adapter version, both transcriber versions, judge model + version + temperature + seed, timestamp, concurrency, mode, and caller-audio SHA-256 hashes.
2. **Adopt reciprocity**: we accept benchmarking of our own products on the same terms. This mirrors the norm and blunts the self-dealing critique.
3. **14-day right of reply + embargo** before any cross-vendor publication, with the vendor's response published unedited alongside.
4. Publish **variance bands from N≥3 runs**, never a single-run point score.
5. Carry the §10.6 framing line on every card.
6. State a **correction policy** and a contact for disputed results.

### 15.8 Recording consent, TCPA, bot disclosure — affirmatively out of scope for v1

Worth stating as a conclusion so hackathon hours are not spent on phantom compliance:

**v1 creates no bot-disclosure, TCPA, or EU AI Act Art. 50 obligation, because there is no PSTN leg and no natural
person on the call.** Federal law and ~38 states use one-party consent and the harness is a party to the call.
EU AI Act Art. 50(1) binds providers of systems "intended to interact directly with natural persons" — our caller
interacts with a bot. California BPC 17941 requires intent to mislead plus a commercial or election purpose.

*Caveat recorded honestly:* the FCC AI-voice declaratory ruling could not be retrieved from primary sources (403 /
undecodable PDF), so that specific holding is marked **unverified** in `docs/legal-notes.md`.

**But two real issues survive, and both need handling:**

1. **The user is not the only recorder.** Vapi records by default (`artifactPlan.recordingEnabled` defaults `true`) and Retell records unless you opt out, with its terms stating recordings may be processed and Vapi's privacy policy stating they "may be retained to help train and improve the AI models." **Retention periods are undocumented for both.** Hence §15.3's suppression-flag requirement and `docs/data-handling.md`.
2. **~12 states require all-party consent** (CA, CT, FL, HI, IL, MD, MA, MT, NH, OR, PA, WA), and *Kearney v. Salomon Smith Barney* extends California's rule extraterritorially. This matters the moment a live human enters the loop — and Retell agents can `transfer_to_human` with no dry-run flag to prevent it.

**First-run blocking warning, shown once, verbatim:**

> This tool records audio and transcripts of every test call. Recordings are stored locally in `./data`. Your
> voice-agent vendor may ALSO record and retain these calls under its own terms, and may use them to improve its
> models. Only test agents you own or are authorized in writing to test. Do not point this tool at an agent
> connected to real customer data. If a live human can be reached by this agent (call transfer, escalation), disable
> that path before running: several jurisdictions require all-party consent to record, and this tool cannot obtain it.

**Keeping SIP out of v1 is a legal design win, not just a scope cut** — say so in the PRD and the README, because it
protects the decision from well-meaning scope creep during the hackathon. All three analyses above invert the moment
a PSTN leg exists (§20).

### 15.9 Side-effect containment

Real agents do real things. Retell agents execute `transfer_to_human`, send SMS, book appointments, and call
arbitrary customer APIs; JustCall's action enum includes `appointment_scheduled`, `call_transfer`, `send_sms`,
`ivr_navigation`. **Neither Retell nor Vapi documents any test mode, sandbox, or dry-run flag.** Retell's own
simulation docs concede that unmocked tools hit real endpoints so "a test can create a real booking or charge."

Fifty adversarial calls against a production agent can therefore book 50 real appointments, fire 50 real SMS, or page
a real on-call human 50 times at 3am — and the suite is *designed* to manipulate the agent, so jailbreak personas
actively optimise toward unauthorised tool invocation.

Requirements:

1. **`side_effects` in the capability registry** per adapter, plus whether the vendor offers any suppression (Retell/Vapi: **UNAVAILABLE**).
2. **Pre-flight fetches and displays the agent's tool list** where the API exposes it, and requires explicit acknowledgement that these tools **will fire for real**.
3. **Irreversible tools** (transfer, SMS, payment, booking, outbound write) **block the run** unless `--allow-side-effects` plus a staging attestation.
4. **Ship a tiny mock webhook server** and document cloning the agent with webhooks pointed at it — making the safe path the easy path is worth more than a warning.
5. **Every observed tool call appears in the report as a side-effect warning**, not merely as assertion input.
6. Turn and duration caps (§8.8) are the only backstop on side-effect *volume* — the coupling is stated explicitly so it is not lost.

### 15.10 Cost blowout

The budget governor bounds *our estimate*, not the vendor's meter, and Vapi's terms put overspend squarely on the
customer. The only control that actually binds is a **vendor-side spend cap**, which is why pre-flight instructs the
user to set one and records their attestation (§8.2). See §8.7 for the mechanism and the $60/run arithmetic.

### 15.11 Model-provider AUP

The caller and judge run on someone's LLM, and generating prompt-injection payloads may be restricted by that
provider's own AUP. Anthropic's AUP, for example, prohibits attempts to "bypass capabilities, restrictions, or
guardrails… for the purposes of instructing the model to produce harmful outputs (e.g., jailbreaking or prompt
injection) **without prior authorization from Anthropic**," and separately bars circumventing "the guardrails or
terms of other platforms or services."

Requirements: an `llm_provider_aup` note per selectable caller/judge model with the clause quoted and dated; the
§15.4 attestation cited as the "authorization of the system owner" basis; **a static, human-authored, cited corpus
preferred over live generation of novel attacks** (§15.5 — which the determinism goal already pushes toward, so it
is a free win); and LIVE-mode improv restricted to benign conversational connective tissue, never to generating the
attack itself. OpenAI's service terms returned 403 and are marked unmapped.

---

## §16. Data Model

### 16.1 Storage

SQLite + files under `./data`. No Docker, no Postgres, no compose.

### 16.2 Core entities

`run` (id, suite_version, mode, adapter, agent_version_tuple, concurrency, judge_config, transcriber_versions,
terminal_state, run_status, budget_caps, started_at, ended_at, replication_bundle_hash)
→ `call` (id, run_id, persona_id, status[`passed|failed|skipped|not_executed`], duration, cost_actual,
cost_estimated_flag, vendor_call_id, audio_paths, latency_metrics, concurrency_blocked_flag)
→ `turn` (call_id, seq, role, t_start_ms, t_end_ms, text_pinned_stt, text_pyai_stt, text_vendor, tokens)
→ `assertion_result` (call_id, assertion_id, blocking, verdict, evidence_class, evidence_offsets, judge_critique)
→ `quarantine` (call_id, offsets, raw_span) — **excluded from all exports**
→ `attestation` (run_id, type, text, timestamp)
→ `dispute` (call_id, assertion_id, user_label, note)

### 16.3 Shaped for production ingest

A production call must later ingest as a **run-of-one** without a schema migration: `run.mode` gains an `observed`
value, `call.persona_id` becomes nullable, and the assertion path is unchanged. This is a schema commitment now,
feature later (§2.2).

### 16.4 Redaction at the boundary

A **denylist enforced at the persistence and logging boundary**, not at the export step. Vapi's
`transport.websocketCallUrl` is the motivating case: no Vapi doc states whether that URL requires auth (every
published sample is a bare `new WebSocket(url)`), so if it is unauthenticated the URL is a **bearer secret**. Store
only the `callId` and reconstruct the URL in memory at connect time; never let it reach SQLite, stdout, or an
exported report. Users paste run records into GitHub issues.

---

## §17. Open Questions for the Engineer (SDK — §9 of the original question set)

Deliberately unanswered here; these are the SDK owner's calls.

1. **Core language: Python or TypeScript?** Python has the audio/STT ecosystem (Whisper, Silero VAD, `jiwer`, pipecat's evals as reference) and matches where voice work lives; `uvx vsim` is a clean one-liner. TypeScript gives one language across SDK + UI, `npx vsim` is a better-known entry point, and the contributor funnel is larger. **This is effectively irreversible by day 2** — decide before the first commit. (Note: whichever is chosen, the UI is TS, so a cross-language boundary exists either way; the question is which side of it the run engine sits on.)
2. **Is the CLI a strictly thin wrapper?** Recommended yes, no duplicated logic. Confirm and enforce with a lint rule or an import boundary check.
3. **SDK primitives.** Proposed: `Suite`, `Persona`, `Adapter`, `Judge`, `Transcriber`, `Run`, `CallResult`, `BudgetGovernor`. A custom scorer is a subclass + register. Does this decomposition survive contact with the run loop?
4. **Second-language SDK in v1?** Recommended no — one, done well.
5. **Plugin discovery mechanism** for out-of-tree adapters (entry points? directory convention?). Documented from day one even though v1 adapters are in-tree.
6. **Async model** — asyncio/trio vs threads for 50 concurrent duplex sockets plus serialized writes. Which back-pressure primitive? (LiveKit's `AudioSource.capture_frame` blocks until its 50 ms buffer accepts the frame, giving pacing for free; is there an equivalent on the chosen stack?)
7. **Audio resampling strategy** across providers: PyAI 24 kHz PCM16 tagged frames, Vapi 16 kHz `pcm_s16le` raw binary, ElevenLabs base64 with a 7-value format enum, Retell via LiveKit. Where does resampling live — adapter or core?
8. **Packaging the UI inside the CLI distribution** — build step, static assets, versioning.
9. **Test strategy for the harness itself** — how do you test a thing whose job is testing? (A recorded-fixture transport is the likely answer.)

---

## §18. Hour-One Empirical Probes

Each of these is a documented unknown that gates a design decision. **All must run in the first hours, before the
dependent code is written.** Results get recorded in the PRD as an appendix.

| # | Probe | Gates | Currently |
|---|---|---|---|
| 1 | **PyAI Omni concurrent-session ceiling** | Concurrency defaults, whether 50 is claimable at all | Unpublished — "set by your plan" on every page checked |
| 2 | **Omni `seed`/`temperature` A/B** — same config twice, diff the audio | Confirms LIVE mode is non-deterministic as documented | Docs say "honored once the engine supports them"; changelog never mentions them |
| 3 | **Vapi WebSocket auth mechanism** — header? query token? subprotocol? none? | Vapi adapter design + the §16.4 redaction requirement | Undocumented; every sample is a bare `new WebSocket(url)` |
| 4 | **Vapi downlink: agent-only or mixed?** Send a distinctive caller tone, check whether it echoes back | Whether live scoring works or must fall back to post-call per-channel artifacts (§4.3) | Docs say "bidirectional" and "binary audio data", never which |
| 5 | **Do `vapi.websocket` calls consume concurrency slots?** | Whether a 50-wide fan-out silently serialises at the default 10 | Concurrency page discusses only phone calls; billing implies yes |
| 6 | **Omni `call_id` discovery + transcript 404 race window** | Whether `fetch_vendor_transcript` is viable for PyAI at all | Docs never state where `call_id` is emitted during a session; transcript route 404s until the engine pushes the record |
| 7 | **ElevenLabs base64 throughput at concurrency** | Whether base64 framing is a bottleneck at 10+ | Undocumented |
| 8 | **Retell web-call 30-second start window under load** | Whether concurrent `create-web-call` tokens expire before we connect | Documented window, untested at fan-out |

Probe 3 and probe 4 are the two on the critical path. Assign them first.

---

## §19. The 33 Hours

### 19.1 Team split

| Who | Owns |
|---|---|
| **Eng 1** | SDK core: run engine, harness loop, budget governor, artifact store, adapters (Vapi + Retell) |
| **Eng 2** | Caller driver (REPLAY + LIVE), transcribers, judge, scorer, CLI; adapters (PyAI + ElevenLabs) |
| **Designer** | Report card, the three-layer timeline, live run grid, README hero |
| **Growth/PM** | The 50 personas as YAML with citations, industry packs, `pricing.yaml` seed, demo agent failure modes, README, launch |

The personas and `pricing.yaml` are content, not code — which is why they sit with the non-engineer and why they can
proceed in parallel from hour 0. This is also the deck's point that non-engineers can win any of the five trophies.

### 19.2 Rough sequence

**Hours 0–4:** probes 3 and 4 running; SDK skeleton + adapter interface frozen; local demo agent stood up; persona
schema frozen so content work can start.
**Hours 4–12:** run engine + REPLAY caller + pinned transcriber + rule-based assertions; Vapi adapter; first
end-to-end call against the demo agent.
**Hours 12–20:** judge + scorer; Retell and PyAI adapters; report card; CLI complete with exit codes.
**Hours 20–26:** UI (grid + timeline); ElevenLabs adapter; cost model; MCP.
**Hours 26–30:** N=30 calibration labelling (serial, needs the judge working — this is why it cannot start earlier);
safety gates; README + screenshot.
**Hours 30–33:** verification pass (§22), demo rehearsal, buffer.

### 19.3 Cut order if behind at hour 24

Cut in this order: **MCP → run comparison → dispute/label flow → ElevenLabs adapter → LIVE mode.**

**Never cut:** the local demo agent, the timeline, the report card, the safety gates. The first three are the demo;
the fourth is the thing that makes shipping it responsible.

### 19.4 The 90-second demo

Connect Vapi → pick agent → 50 tiles go live → 11 turn red → open a red one → combined timeline → play audio → hear
the agent say something unhinged at 0:47 → the assertion flag is pinned exactly there → card renders → grade D+ →
cost per resolved call → run twice, identical hash, identical score.

**Rehearsed against the local demo agent**, which has no vendor concurrency ceiling and no ToS exposure (§15.6).

---

## §20. Roadmap

**v1.1 — BYO-Twilio + SIP transport.** Unlocks JustCall, Synthflow, and the ~8 telephony personas already authored
with `requires_capability: [dtmf]`. **Gated on a compliance section covering:** called-party consent, all-party-consent
jurisdictions (12 states + *Kearney* extraterritoriality), AI-voice disclosure at call start, and DNC scrubbing.
Retell's own customer Addendum is the ready-made checklist (disclose recording and obtain consent; all-party states
must announce and obtain verbal consent; no misleading about artificial identity; DNC scrub every 31 days; retain
consent records 5 years). **This gate is mandatory — the whole §15.8 analysis inverts the moment a PSTN leg exists.**

**v1.1 — Deepgram adapter.** Ships `InjectAgentMessage` with `behavior: interrupt` — the only documented
deterministic barge-in primitive found in the market — plus a `LatencyReport` event with full stt/ttt/tts breakdown
and 45 concurrent connections on pay-as-you-go. Caveat: no post-call artifacts at all, so it exercises the
`Unsupported` sentinel path (§7.1).

**v1.2 — Judge panel.** Three cheap disjoint-family judges (§9.4). Better kappa than a single frontier judge at 7–8×
lower cost. Highest-value quality upgrade available.

**v1.2 — Audio-native scorers.** Frustration, emotion, overlap detection, prosodic adaptation. Full-Duplex-Bench's
parameter set (speaking rate, pitch mean/SD, intensity, predicted MOS with paired t-tests) is the reference.

**v1.3 — Public leaderboard.** Repo-based: submissions are PRs adding a signed `result.json`; a GitHub Action verifies
the replication bundle and rebuilds a static board. Zero infra, self-verifying, and the PR stream is the social proof.
Requires `PUBLISHING.md` (already shipped in v1) plus seeded reference agents we build and own.

**v1.3 — Production monitoring.** Ingest a real call as a run-of-one; the schema already allows it (§16.3).

**v2 — Prompt-aware persona generation.** Opt-in prompt reading unlocks generated scenarios and prompt-level
remediation (§10.5).

---

## §21. Decision Log

### 21.1 Open items

| Item | Status |
|---|---|
| **Name.** `Voice-Agent-Grader` is a placeholder. Must not be PyAI-branded — neutrality is the thesis. | Open; GitHub org exists |
| **SDK language** (§17.1) | Engineer's call, needed before first commit |
| **Community sentiment research** for naming/positioning | **Blocked** — firecrawl is not installed (no binary, `FIRECRAWL_API_KEY` empty) and `reddit.com` is unfetchable in this environment. Needs a real firecrawl install or another source. |
| PyAI Omni concurrency ceiling | User is obtaining; probe 1 as backstop |

### 21.2 Decisions reversed by research

Four locked decisions were overturned after reading provider and competitor documentation. Recording them with cause
so reviewers can audit the reasoning:

| Decision | Was | Now | Cause |
|---|---|---|---|
| v1 adapters | Vapi + Retell + PyAI + **JustCall** | Vapi + Retell + PyAI + **ElevenLabs** | JustCall is hard PSTN-only: E.164 required, no WS/WebRTC/SIP anywhere in the API, 5 calls/min cap |
| Scoring transcriber | **PyAI-pinned, not swappable** | **Dual-transcribe** (pinned Whisper + PyAI Hear), divergence published | Sponsor-owned instrument scoring competitors' audio is a credibility kill shot; determinism needs a pinned *version*, not a pinned *vendor* |
| Determinism | temp-0 + seed + improv + byte-identical replay | **Two modes; REPLAY default** | Omni seed/temperature are documented-but-inert, and improv + byte-identical replay are mutually exclusive |
| Framing | "compare vendors" | **"test your own agent"** | Retell ToS §10.1(d) prohibits benchmarking without written consent |

### 21.3 Decisions confirmed against research

WebSocket-only v1 with a modular transport (also a legal win, §15.8) · beat-spine ordering · blocking/advisory
assertions · 12 turns / 180 s modifiable caps · the four-part context formula into both caller and judge · never
reading the prompt in v1 · difficulty tiers on the card · re-transcribe rather than trust the vendor · in-tree
adapters with a documented plugin protocol · capability-driven auto-skip · agent listing with demo-only manual paste
· no inbound · all seven harness parts · concurrency 10 default · ≥60% rule-based assertions · published judge
calibration · per-test scores + remediation on the card · one combined waveform · SQLite + files · bundled UI ·
production-ingest-shaped records · dispute → public golden set · community `pricing.yaml` · two cost lines ·
cost-per-resolved-call · local-first with explicit publish gate · MCP with 6 tools · MIT · zero-key demo agent.

### 21.4 The one genuinely lucky finding

`AgentConfig.persona_perspective: caller` — PyAI documents it as "the persona is the individual on the call instead,
**as in QA and simulation callers**," and in that mode drops the operator-voice layer "so it cannot contradict an
inverted persona." The sponsor's product ships a first-class simulated-caller mode. This was not assumed; it removes
the largest technical risk in LIVE mode, and it means using PyAI here is a genuine fit rather than a sponsorship
obligation.

---

## §22. Verification

### 22.1 Design-gating probes

All eight probes in §18 must return before the dependent code is written. Probe 3 (Vapi WS auth) and probe 4 (Vapi
downlink mixed vs agent-only) are on the critical path.

### 22.2 End-to-end acceptance gates

| # | Gate | Pass condition |
|---|---|---|
| 1 | **Cold start** | Fresh clone, no keys, no Docker → `vsim run --demo` → rendered card in < 5 min (target < 60 s) |
| 2 | **Determinism** | Two REPLAY runs, same agent version → identical caller-audio SHA-256 set **and** identical score |
| 3 | **Rule-based stability** | Flip rate across 3 identical REPLAY runs ≈ 0; if not, the assertion is misclassified |
| 4 | **Budget gate** | Set a cap that trips mid-run → terminal state `deadline`/`budget_aborted`, unrun tests `not_executed`, **no average or grade rendered**, headline reads `INCOMPLETE: n/50 executed` |
| 5 | **Authorization gate** | Pasting a third-party agent ID without an enumerating credential is **refused**; a sandbox key cannot drive a third-party adapter |
| 6 | **Leak guard** | Grep a completed run's SQLite + logs + exported report for `websocketCallUrl`, API keys, and raw PII → zero hits; PII appears only as typed tokens, raw spans only in `quarantine` |
| 7 | **Side-effect gate** | An agent with a transfer or SMS tool blocks the run without `--allow-side-effects` + attestation |
| 8 | **Capability skip** | A DTMF persona on a WebSocket adapter reports `skipped: capability unavailable` — never `failed` |
| 9 | **Version guard** | `vsim compare` across differing agent-version tuples refuses and explains |
| 10 | **Concurrency honesty** | Force queueing → affected calls' latency metrics marked invalid, not reported |
| 11 | **CI contract** | `--fail-under` returns exit 1 below threshold, 0 above; `--junit` parses in a standard runner |
| 12 | **Three front doors, one path** | CLI, UI, and MCP `run_suite` produce byte-identical run records for the same config |
| 13 | **Judge disclosure** | The card and `report.md` carry the full replication bundle and the §10.6 framing line |
| 14 | **Calibration published** | `docs/judge-calibration.md` exists with N, raw agreement, kappa, false-pass/false-fail, class balance, Wilson CI, and the deferral note |

### 22.3 Pre-launch checklist (deck's ship gate)

MIT licence · public repo · genuine five-minute setup, timed by someone who has not seen the repo · sample data so
the demo needs zero setup · one killer screenshot in the README (demo agent, labelled) · sandbox key self-mints ·
explicit exits, gates, capped retries, budgets · `SECURITY.md` + `RESPONSIBLE_USE.md` + `/.well-known/security.txt`
+ `docs/vendor-tos.md` + `docs/data-handling.md` + `docs/legal-notes.md` + `PUBLISHING.md` · §0 disclosure at the top
of the README.

---

## Appendix A — Sources

All provider claims in this document were read from primary documentation between 2026-08-04 and 2026-08-05. Key
paths: `docs.pyai.com` (`/realtime/omni-protocol`, `/api-reference/agents/update-an-agent`, `/errors-and-limits`,
`/pricing-and-metering`, `/reference/reliability`, `/guides/browser-voice-agent`, `/guides/agent-greeting`,
`api.pyai.com/openapi.json` v1.3.0) · `docs.vapi.ai` (`/calls/websocket-transport`, `/calls/call-concurrency`,
`/assistants/retrieve-call-artifacts`, `/api-reference/calls/*`) · `docs.retellai.com` (`/api-references/create-web-call`,
`/get-call`, `/list-agents`, `/deploy/concurrency`, `/test/llm-simulation-testing`, `/agent/version`) ·
`elevenlabs.io/docs/eleven-agents/*` · `developers.deepgram.com` · `docs.livekit.io/agents/*` · `docs.synthflow.ai` ·
`developer.justcall.io` · `docs.coval.ai` + `github.com/coval-ai/benchmarks` · `hamming.ai` · `github.com/pipecat-ai/pipecat`
(`src/pipecat/evals/*`) · `github.com/ServiceNow/eva` · `github.com/DanielLin94144/Full-Duplex-Bench` + arXiv 2503.04721,
2507.23159 · judge-calibration literature: arXiv 2306.05685 (MT-Bench), 2404.13076 (self-preference), 2305.17926
(Fair Evaluators), 2406.12624 (Judging the Judges), 2404.18796 (PoLL), McHugh 2012 (PMC3900052), lmsys Arena-Hard,
promptfoo, Databricks.

**Marked unverified:** FCC AI-voice declaratory ruling (403 / undecodable PDF) · ElevenLabs Prohibited Use Policy
(404 on four variants) · JustCall ToS (unretrievable) · OpenAI service terms (403) · PlayHT/PlayAI pricing (DNS
failure, invalid TLS, expired certificate) · Ragas calibration docs (HTTP 429 on six attempts) · Coval's full
internal data model (research stream failed mid-response; object vocabulary recovered from its API/CLI/SDK/MCP docs).
