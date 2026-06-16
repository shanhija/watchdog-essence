# Build brief — TypeScript context

Read **[`../../ESSENCE.md`](../../ESSENCE.md)** first; it is the spec. Your job is to build
**`watchdog.ts`** — a service that watches this environment's logs and opens PRs that fix the app.

You are **not** given a watchdog or any of its internals. You are given a normal environment:

- `app/` — a buggy ingest job that logs errors (the code to watch and patch).
- `services/` — working clients you wire together. Read each file for its API; in short:
  - `log_store.FileLogStore(path).fetch()` → `[{ts, level, text}, ...]`
  - `triage_model.FakeTriage().cluster(lines)` → `Incident[]` (`{slug, severity, confidence, rootCause, summary, affectedFiles, sampleLines, occurrences}`)
  - `sandbox.LocalSandbox(root)` → `.writeFiles({path: content})`, `.runTests()` → `{passed, output}`, `.diff()` → string, `.cleanup()`
  - `coding_agent.CannedCodingAgent().attemptFix(incident, sandbox)` → `FixResult` (`{status, diff, files, smokePassed, ...}`)
  - `code_host.LocalCodeHost(prsDir).openPr(slug, title, body, diff, files)` → url
  - `notifier.ConsoleNotifier().send(report)`

## What to build

`watchdog.ts` runnable as `node watchdog.ts`. One pass, per ESSENCE §4:

1. Fetch log lines from the log store.
2. Triage them into incidents.
3. For each **actionable** incident (ESSENCE §9: not `noop`, confidence `medium`/`high`): make a
   sandbox, ask the coding agent to draft a fix, and **only if the fix succeeded** (non-empty diff
   whose smoke tests passed) open a PR via the code host.
4. Send exactly one report per incident via the notifier. Clean up the sandbox.

Default paths: the app log is `app.log` and PRs go under `.prs/` in this folder. Honour ESSENCE §2 —
never touch the real working tree (the fix is drafted in the sandbox and delivered as a PR), a human
merges.

Stay in **erasable TypeScript** (no enums/namespaces/parameter-properties) so it runs under Node's
native type-stripping with no build step. The essence also describes a datastore role for dedup; for
this single-pass demo the triage clustering is enough.

## Verify

```bash
node demo.ts     # must end with "HEALED"; non-zero exit on any failure
```
