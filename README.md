# Wiretap

[License: MIT](LICENSE)
[Python 3.11+](https://www.python.org/downloads/)

Open-source voice agent testing. Free. Dials your live agent. Not a copy.

You built an AI that talks to customers. You called it a few times. It seemed fine. That is not a real test.

Wiretap calls the agent you already run — Retell, Vapi, ElevenLabs, LiveKit, Synthflow, or a phone number — and acts like a hard caller. Angry. Fast. Confusing. Trying to trick it. Then it scores the call (rules + LLM judge) and stores results under `~/.wiretap/` (override with `WIRETAP_HOME`).

Paid tools charge hundreds a month for this. Hamming is about $500/mo. This is a git clone.

```text
   ┌─────────────┐         dial          ┌──────────────────┐
   │   WIRETAP   │ ───────────────────▶  │ Your live agent  │
   │  test agent │   web / phone / text  │  (Retell, Vapi…) │
   │  + judge    │ ◀───────────────────  │                  │
   └─────────────┘         reply         └──────────────────┘
```

---



## What it is

A **voice agent** is an AI that talks on a call. Booking, support, sales — same idea.

**Wiretap is a test harness.** It pretends to be the caller. It talks to your *live* agent — the one customers would actually reach — not a local replica. Then it tells you if the agent held up.

It runs on your computer. From the terminal, or a local UI. Nothing phones home.

---



## Why use it

Calling your own agent a few times is not testing. Your agent has likely never faced:

- An angry customer about a bad charge
- Someone with a heavy accent speaking fast
- A caller who interrupts every two seconds
- Someone trying to jailbreak a refund
- A long call that jumps topics

Wiretap generates those kinds of tests, runs them against the live agent, and scores the result. You can do it once, or every time you ship.

---



## Why choose wiretap

The category is full of paid platforms and open-source tools that don't quite test the real thing.


|                                | Paid tools (Hamming, Cekura, Coval) | Other open source                                     | Wiretap                                 |
| ------------------------------ | ----------------------------------- | ----------------------------------------------------- | --------------------------------------- |
| Price                          | $100–$500+/mo, or per minute        | Free                                                  | **$0** — you only pay your own API keys |
| Tests your live agent          | Yes                                 | Often no — replica, or can't reach the deployed agent | **Yes — default**                       |
| Open source                    | No                                  | Yes                                                   | **Yes (MIT)**                           |
| You can read the scoring logic | No                                  | Rarely disclosed                                      | **Yes — in this repo**                  |
| Runs on your machine           | No (SaaS)                           | Often yes                                             | **Yes — local-first**                   |
| Terminal + CI                  | Usually web or a sales call         | Mixed                                                 | **Yes**                                 |


Hamming, Cekura, and Coval dial live agents too. They also bill you, hide the eval logic, and want a vendor relationship.

VoiceTest tests a local reconstruction by default. ServiceNow/eva is strong research software, but it cannot reach a deployed agent.

Wiretap's job is narrower: **test the agent you actually deployed, for free, with scoring you can read.**

If you need production monitoring, auditor-facing reports, or a hosted dashboard, use a paid platform. If you need to test your live agent from your laptop, use wiretap.

You don't just get a pass/fail. You get the score, the reason, and wording you can apply to the agent.

![Wiretap local UI showing a scored call, what went wrong, and a suggested prompt fix](docs/simulation-improvements.png)



---



## What it's not

- Not a voice-agent builder. It tests agents. It does not create them.
- Not production monitoring. No live ops dashboard.
- Not a hosted SaaS. Results stay in `~/.wiretap/` on your machine.
- Not magic. Voice testing is not fully deterministic. The judge is pinned at temperature `0.0` so scores don't drift on a whim — and that config is in the repo.

---



## Quick start

**You need:** Python ≥3.11, [uv](https://docs.astral.sh/uv/), and API keys for an LLM plus speech (STT/TTS — speech-to-text and text-to-speech). A platform key (e.g. Retell / Vapi) is needed to dial a live agent.

```bash
git clone https://github.com/mohibsaas/wiretap.git
cd wiretap
uv sync
uv tool install --editable .

wiretap init                 # test agent → live agent → suite → optional phone
wiretap simulate -s <suite> --all
wiretap report
```

`wiretap init` writes secrets to `~/.wiretap/.env` only (never into suite YAML). Check config without leaking keys:

```bash
wiretap status
```

> **Tip:** Prefer `uv tool install --editable .` so `wiretap` is on your PATH. `uv run wiretap …` works without installing.



### Minimal path (already have keys)

```bash
# Put keys in ~/.wiretap/.env — see .env.example
wiretap import retell --agent-id agent_xxx
wiretap simulate --suite retell_agent_xxx --all
wiretap report
```

---



## Local UI

A browser dashboard on your machine. Same `~/.wiretap/` data and onboarding as the CLI.

```bash
cd ui && npm install && npm run build && cd ..
wiretap ui run
# → http://127.0.0.1:8787
```

For UI development (hot reload):

```bash
uv run wiretap ui run --no-open          # API on :8787
cd ui && npm install && npm run dev      # Vite proxies /api
```

---



## Optional extras

```bash
uv sync --extra pstn   # real phone calls via Twilio
uv sync --extra mcp    # MCP server for coding agents
uv sync --extra dev    # pytest + ruff
```

**Phone:** web vs phone is a per-run choice (`--transport phone`). Needs Twilio credentials from `wiretap init` (or `.env`).

**MCP:**

```bash
uv sync --extra mcp
uv run wiretap-mcp
```

Cursor example (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "wiretap": { "command": "uv", "args": ["run", "wiretap-mcp"] }
  }
}
```

---



## Commands


| Command            | What it does                                            |
| ------------------ | ------------------------------------------------------- |
| `wiretap init`     | First-run setup (simulator → agent → suite → phone)     |
| `wiretap import …` | Pull a platform agent + generate category tests         |
| `wiretap suite …`  | list / show / categories / generate                     |
| `wiretap simulate` | Dial (`--all` or `--scenario`, `--transport web|phone`) |
| `wiretap report`   | Summarize local simulation artifacts                    |
| `wiretap export`   | Copy a suite out for git or sharing                     |
| `wiretap ui run`   | Local dashboard                                         |
| `wiretap status`   | What’s configured (no secret values)                    |


---



## Platforms


| Platform          | Live dial    | Notes                                    |
| ----------------- | ------------ | ---------------------------------------- |
| Vapi              | WebSocket    | `VAPI_API_KEY`                           |
| Retell            | LiveKit      | `RETELL_API_KEY`                         |
| ElevenLabs Agents | ConvAI WS    | `ELEVENLABS_API_KEY`                     |
| LiveKit Agents    | LiveKit room | `LIVEKIT_API_KEY` + `LIVEKIT_API_SECRET` |
| Synthflow         | WS media     | `SYNTHFLOW_API_KEY` + from/to numbers    |
| Bland / Bolna     | Import only  | Dial via `--transport phone`             |
| Custom / stub     | Text         | `platform: null`, `transport: text`      |
| Phone / PSTN      | Twilio SIP   | `uv sync --extra pstn`                   |


Secrets belong in `~/.wiretap/.env` or the environment. Suite YAML stores agent ids and `token_env` **names**, never key values. See [`.env.example`](.env.example).

---



## How scoring works

- **Rules** check hard constraints from the suite.
- **LLM judge** scores goal match (pass / partial / fail).
- **Suggestions** appear on failures only.
- Optional **advisor** can suggest config fixes after failing calls.

Test categories used for generation: `emotional`, `linguistic`, `adversarial`, `operational`, `factual`, `compliance`, `task`, `other`.

Your agent can *say* it booked an appointment. Wiretap can also check whether the tool call actually fired.

---



## Data layout

```text
~/.wiretap/          # or $WIRETAP_HOME
  .env               # secrets (from wiretap init)
  suites/            # YAML suites
  simulations/       # call artifacts + transcripts
  evaluations/       # run summaries + live progress
  onboard.json
```

Architecture notes: [docs/HLD.md](docs/HLD.md).

Default speech (STT/TTS) is PyAI. You can use other providers. You pay those APIs yourself — there is no wiretap bill.

---



## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).

Security reports: [SECURITY.md](SECURITY.md) — please use private disclosure, not public issues.

```bash
uv sync --extra dev
uv run ruff check src tests
uv run pytest -q
```



## License

[MIT](LICENSE)