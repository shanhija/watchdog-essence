# Python context

This folder is a small, ordinary **environment** — a running app and the services around it.
There is **no watchdog here**. Building one is the exercise.

## What's here

- **`app/`** — a tiny data-ingest job. Run it and it logs some errors, because it has a bug
  (it drops records that are missing a `price` field). This is the code that produces the logs —
  and the code a watchdog would patch.
- **`services/`** — the things you already run, as simple local fakes:
  | service | what it is |
  |---|---|
  | `log_store.py` | reads the app's log file (your log aggregation) |
  | `triage_model.py` | clusters log lines into incidents (a fake LLM; real seam `LLMTriage`) |
  | `sandbox.py` | an isolated copy of the app to draft + test a fix in |
  | `coding_agent.py` | drafts a fix in the sandbox and runs the app's tests (real seam `CLICodingAgent`) |
  | `code_host.py` | opens a PR (records it under `.prs/`) |
  | `notifier.py` | delivers the incident report (prints it) |
- **`run_app.py`** — runs the app once (produces logs).
- **`demo.py`** — the end-to-end check (also the acceptance test).

## The exercise

Open this folder in your coding agent and prompt:

> **"Build me a service from this essence in this context."**

(the essence is [`../../ESSENCE.md`](../../ESSENCE.md)). The agent builds **`watchdog.py`** — a
service that reads the app's logs from the log store, triages them, uses the sandbox + coding agent
to draft a fix to **the app's own code**, opens a PR via the code host, and reports via the notifier.

When it's built, the whole loop runs:

```bash
python3 run_app.py     # the buggy app logs errors
python3 watchdog.py    # the watchdog opens a PR that fixes app/ingest.py
python3 demo.py        # BEFORE -> watchdog -> merge the PR -> AFTER (errors gone)
```

`python3 demo.py` is the proof: a bug becomes a log becomes a fix becomes a PR, and merging that PR
makes the app run clean. Needs only **Python 3.9+**, no dependencies. See [`AGENTS.md`](AGENTS.md).
