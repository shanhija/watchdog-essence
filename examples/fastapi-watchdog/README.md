# Reference build: a watchdog service from the `fastapi` context

**This is an *output*, not a context.** It's the result of handing a fresh Claude agent the spec plus the
plain [`fastapi`](../../contexts/fastapi/) environment and saying *"build me a service from this essence in
this context."* It's here so you can see what a finished build looks like — including the decisions the
agent had to make on its own.

> 🙈 **Spoiler.** The point of the repo is to build this *yourself*. For the exercise, start in
> [`../../contexts/fastapi/`](../../contexts/fastapi/) and don't read ahead — then come back to compare.

## How it was produced

A headless `claude` (model `claude-opus-4-8`), given only `ESSENCE.md` + the watchdog-agnostic fastapi
context, ran ~19 minutes / 62 turns and produced everything here. **73/73 tests pass offline.** The code is
the agent's, with **two small fixes applied after testing it live** against a real Loki + a real Anthropic
key: the coding-agent CLI now runs with full autonomy in its sandbox (so it can run the gate + commit
headless), and the fix diff excludes the agent's own tooling artifacts. Both were fed back into the spec
(`ESSENCE.md` §4E, Appendix D, lessons 14–15). (Otherwise only the `.venv`, caches, and a duplicated
`ESSENCE.md` were stripped.)

## What the agent built

A complete resident **`watchdog` service** implementing the full ESSENCE §4 pipeline, deployed as another
service in [`docker-compose.yml`](docker-compose.yml) beside the app it watches:

- `watchdog/` — `logstore.py` (Loki), `triage.py` (Claude, forced tool-call), `agent.py` (Claude Code CLI,
  headless), `sandbox.py` (pristine `git`-init copy), `store.py` (SQLite, 4 tables), `fingerprint.py`
  (3 dedup keys), `remedy.py` (3-tier dedup), `pipeline.py` (dispatch), `service.py` (the resident loop +
  health endpoints), `jobs.py` / `ops.py` (periodic + operator actions), `budget.py`, `locks.py`, …
- [`watchdog/Dockerfile`](watchdog/Dockerfile) — the service image ships the app's test runtime **and** the
  Claude Code CLI, so the coding agent runs headless *inside the container*, credentialed by env — not a
  host run.
- `tests/` — 70 deterministic tests (no network/model/sandbox), plus `tests/test_fix_path.py`, which runs
  the real sandbox + smoke gate **token-free** (a scripted agent applies the `KeyError`→404 fix and the
  app's own `pytest` gates it green).

## The most interesting file: [`watchdog/DECISIONS.md`](watchdog/DECISIONS.md)

The essence says *"where a role is missing or a choice is ambiguous, ask the user with suggestions."* This
run was non-interactive, so the agent wrote every such question + the default it chose into `DECISIONS.md`:
no datastore → **SQLite**; no code host → **auto-PR off** (diff in the report); no notifier → **file sink**;
deploy target → **a service in `docker-compose.yml`**; not a git repo → **`git init` per sandbox**; LLM →
**Claude**. That file is the clearest evidence the spec drives the discovery.

## Running it (needs credentials)

```bash
export ANTHROPIC_API_KEY=...     # the triage + coding-agent roles are LLM-backed (ESSENCE §6)
docker compose up --build         # app + Loki + the watchdog service
./seed.sh                          # generate the errors
```

Auto-PR ships **off** (ESSENCE §9): you get a tested draft fix in `reports/`, zero branch risk.

## Honest caveats (the agent's own, kept as-is)

- It defaulted to `ANTHROPIC_API_KEY` for both AI roles; a subscription-only setup would mount the Claude
  CLI credential into the container instead.
- **The PR-push step is intentionally left incomplete.** The GitHub adapter builds the right PR (title,
  body, the committed `bot/…` branch + diff) and opens it over the API — but the prerequisite, pushing that
  branch to a real remote with a compare-and-swap (`git push --force-with-lease`), is a deliberate stub. It
  depends on your remote, auth, and branch-protection setup, so it's left for you to wire when you turn
  auto-PR on; the default posture (auto-PR off → tested diff in the report) works without it. This is a good
  example of the kind of seam the spec expects you to finish in your own environment (see the repo README).
  Flagged in `watchdog/codehost.py` + `DECISIONS.md`.

The spec it grew from is [`../../ESSENCE.md`](../../ESSENCE.md); the prompts behind the spec are in
[`../../MAKING-OF.md`](../../MAKING-OF.md).
