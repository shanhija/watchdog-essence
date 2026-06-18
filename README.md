# Watchdog Essence

**Write one spec. Hand it to a coding agent. Watch it build a self-healing watchdog that finds and
fixes a real bug — in Python *and* TypeScript.**

This repo is a demonstration of an **"essence"**: a distilled, technology-agnostic spec of a whole
system, written so you can hand it to an AI and have it regrow the system in *your* environment.

<p align="center">
  <img src="claude.gif" alt="A coding agent reads ESSENCE.md, writes the watchdog, and it fixes a real bug" width="820">
</p>

<p align="center"><em>A coding agent reads <code>ESSENCE.md</code> and writes the watchdog from scratch — then it finds and fixes a real bug.</em></p>

## See it heal

Each context ships a tiny buggy app and the services around it — but **no watchdog**. An agent builds
the watchdog from [`ESSENCE.md`](ESSENCE.md); then `demo` runs the whole loop: the app logs an error →
the watchdog drafts a fix to the app's **own** code in a sandbox → opens a PR → and merging it makes
the app run clean.

<p align="center">
  <img src="demo_python.gif" alt="The closed loop running in the Python context" width="760"><br>
  <em>The closed loop — Python.</em>
</p>

<p align="center">
  <img src="demo_typescript.gif" alt="The closed loop running in the TypeScript context" width="760"><br>
  <em>…and the same essence, rebuilt in TypeScript.</em>
</p>

## Try it (the whole point)

`cd` into a context and prompt your coding agent:

> **"Build me a service from this essence in this context."**

The agent reads `ESSENCE.md` + the context's `AGENTS.md` and writes the watchdog. Then prove it:

| Context | Stack | Build target | Prove it |
|---|---|---|---|
| [`contexts/python/`](contexts/python/) | Python 3.9+, stdlib only | `watchdog.py` | `python3 demo.py` |
| [`contexts/typescript/`](contexts/typescript/) | Node ≥ 22.6, runs `.ts` natively — no build | `watchdog.ts` | `node demo.ts` |
| [`contexts/fastapi/`](contexts/fastapi/) | Python + FastAPI, **real** Loki + Claude | a `watchdog` service in `docker-compose.yml` | [reference build →](examples/fastapi-watchdog/) |

The first two share one scenario, so one spec demonstrably produces the same closed loop in two stacks
with *fake* services — yet a **real** fix and the app's **real** tests, so it closes with no API key.
The third, [`fastapi/`](contexts/fastapi/), swaps the fakes for the real things: a FastAPI app shipping
logs to a real **Loki**, triaged and fixed by **real Claude** (your `claude` login, or an API key). Same
essence, all the way to production-shaped. A fresh agent's build of that context lives in
[`examples/fastapi-watchdog/`](examples/fastapi-watchdog/) — a complete deployable service, including the
`DECISIONS.md` it wrote where the environment left a choice open.

**What you get, and what you finish.** The essence builds the *bulk* of the watchdog for you — the
pipeline, the state model, the prompts, the deployment shape. In a real environment, some parts will still
need implementing or tweaking to fit your stack (a code host's push, an auth detail, a log-query quirk) —
that's expected, not a shortfall. You finish the job the way the spec itself says to build it: **stand up
your stack, drive a real error end-to-end, and iterate on what breaks** until it heals. (The reference
build's PR-push is one such intentionally-left seam.)

## How a context is laid out

```
contexts/<stack>/
├── app/            # the buggy log-producing service (watched AND patched)
├── services/       # the things you already run, as fakes:
│                   #   log_store · triage_model · sandbox · coding_agent · code_host · notifier
├── run_app.*       # produce some logs
├── watchdog.*      # ← BUILD ME (the agent writes this, from the essence)
├── demo.*          # the end-to-end proof: BEFORE → watchdog → merge the PR → AFTER
└── README · AGENTS
```

(That's the two stdlib contexts. The [`fastapi/`](contexts/fastapi/) context is the real-infra shape
instead — a FastAPI app + a `docker-compose.yml` with real Loki, no fakes and no stub — where the agent
builds a watchdog **service** into the compose. See [`examples/fastapi-watchdog/`](examples/fastapi-watchdog/)
for what that produces.)

## What an "essence" is

> The distilled functional core of a working system — its invariants, contracts, state model, and
> hard-won lessons, with every vendor or tool abstracted to a *role* — written so an LLM with access
> to your environment can regrow it in your stack. Not a tutorial, not a product, not a project-bound
> spec: a *transplantable* definition. The contexts here are the proof: one spec, the same bug found and
> fixed in Python and TypeScript, then rebuilt as a real deployable service against Loki + Claude.

## How it was built

This whole repo — the spec, then the contexts — was built by prompting an AI coding assistant. The
actual prompts, verbatim and in order, are in **[MAKING-OF.md](MAKING-OF.md)**. (Fittingly: *the
prompts are the spec.*)

## License

[MIT](LICENSE).
