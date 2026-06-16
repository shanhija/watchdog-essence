# TypeScript context

The same exercise as the Python context, in a different stack. This folder is a small, ordinary
**environment** — a running app and the services around it. There is **no watchdog here**; building
one is the exercise.

## What's here

- **`app/`** — a tiny data-ingest job. Run it and it logs errors, because it has a bug (it drops
  records missing a `price` field). This is the code that produces the logs — and the code a watchdog
  would patch.
- **`services/`** — the things you already run, as simple local fakes:
  | service | what it is |
  |---|---|
  | `log_store.ts` | reads the app's log file (your log aggregation) |
  | `triage_model.ts` | clusters log lines into incidents (a fake LLM; real seam `LLMTriage`) |
  | `sandbox.ts` | an isolated copy of the app to draft + test a fix in |
  | `coding_agent.ts` | drafts a fix in the sandbox and runs the app's tests (real seam `CLICodingAgent`) |
  | `code_host.ts` | opens a PR (records it under `.prs/`) |
  | `notifier.ts` | delivers the incident report |
- **`run_app.ts`** — runs the app once (produces logs).
- **`demo.ts`** — the end-to-end check (also the acceptance test).

## The exercise

Open this folder in your coding agent and prompt:

> **"Build me a service from this essence in this context."**

(the essence is [`../../ESSENCE.md`](../../ESSENCE.md)). The agent builds **`watchdog.ts`** — a service
that reads the app's logs, triages them, uses the sandbox + coding agent to draft a fix to **the app's
own code**, opens a PR via the code host, and reports via the notifier. Then:

```bash
node run_app.ts     # the buggy app logs errors
node watchdog.ts    # the watchdog opens a PR that fixes app/ingest.ts
node demo.ts        # BEFORE -> watchdog -> merge the PR -> AFTER (errors gone)
```

## Running it

Needs **Node ≥ 22.6** — it runs `.ts` directly via native type-stripping, **no install required**
(on Node 22.6–23.5 add `--experimental-strip-types`; on 23.6+/24 it's the default). Optional
type-checking is the only thing that needs deps:

```bash
npm install && npm run typecheck
```

`node demo.ts` is the proof: a bug becomes a log becomes a fix becomes a PR, and merging it makes the
app run clean. See [`AGENTS.md`](AGENTS.md).
