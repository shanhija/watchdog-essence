# Build brief — Python context

Read **[`../../ESSENCE.md`](../../ESSENCE.md)** first; it is the spec. Your job is to build
**`watchdog.py`** — a service that watches this environment's logs and opens PRs that fix the app.

You are **not** given a watchdog or any of its internals. You are given a normal environment:

- `app/` — a buggy ingest job that logs errors (the code to watch and patch).
- `services/` — working clients you wire together. Read each file for its API; in short:
  - `log_store.FileLogStore(path).fetch()` → `[{ts, level, text}, ...]`
  - `triage_model.FakeTriage().cluster(lines)` → `[Incident(slug, severity, confidence, root_cause, summary, affected_files, sample_lines, occurrences), ...]`
  - `sandbox.LocalSandbox(root)` → `.write_files({path: content})`, `.run_tests()` → `(passed, output)`, `.diff()` → str, `.cleanup()`
  - `coding_agent.CannedCodingAgent().attempt_fix(incident, sandbox)` → `FixResult(status, diff, files, smoke_passed, ...)`
  - `code_host.LocalCodeHost(prs_dir).open_pr(slug, title, body, diff, files)` → url
  - `notifier.ConsoleNotifier().send(report_dict)`

## What to build

`watchdog.py` with a `main()` runnable as `python3 watchdog.py`. One pass, per ESSENCE §4:

1. Fetch log lines from the log store.
2. Triage them into incidents (the triage model clusters + classifies).
3. For each **actionable** incident (ESSENCE §9: not `noop`, confidence `medium`/`high`): get a
   sandbox, ask the coding agent to draft a fix, and **only if the fix succeeded** (a non-empty diff
   whose smoke tests passed) open a PR via the code host.
4. Send exactly one report per incident via the notifier. Clean up the sandbox.

Default paths: the app log is `app.log` and PRs go under `.prs/` in this folder (the code host +
log store take those paths). Honour ESSENCE §2 — especially: never touch the real working tree (the
fix is drafted in the sandbox and delivered as a PR), and a human merges.

The essence also describes a **datastore** role for dedup across polls; for this single-pass demo
the triage model's clustering is enough, but read ESSENCE §5/§12 if you want to add it.

## Verify

```bash
python3 demo.py     # must end with "HEALED"; exits non-zero on any failure
```
