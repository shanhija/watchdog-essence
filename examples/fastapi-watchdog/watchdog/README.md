# watchdog

A resident service that watches `kvstore`'s error logs, clusters them into **incidents**,
and — for the small, well-understood ones — drafts a tested fix and delivers it for a human
to approve. Grown from [`../ESSENCE.md`](../ESSENCE.md); role mapping in [`DECISIONS.md`](DECISIONS.md).

It does first-line incident response while you sleep, and never touches production: it drafts
against a pristine, isolated copy and proposes (a report, optionally a PR into the review
branch) — automation proposes, humans merge.

## The pipeline (ESSENCE §4)

```
LOG STORE → (A) ingest+dedup → (B) select candidates → (C) one triage-model call
         → (D) dispatch (link / create / benign) → gate
         → (E) fix in a sandbox → (F) smoke gate → (G) remedy dedup → (H) deliver one report
```

Everything expensive is gated, budgeted, and deduplicated at the line, incident, **and** fix
level. The datastore is the source of truth, so a restart drops nothing and re-alerts nothing.

## Run it (in the compose stack)

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # the triage model + coding agent need it
docker compose up --build                   # brings up loki, app, watchdog, grafana
./seed.sh                                    # generate some kvstore errors (the KeyError bug)
# watch the watchdog work:
curl -s localhost:8080/metrics | python3 -m json.tool
ls watchdog_data/reports                     # (inside the watchdog-data volume) one report per incident
```

With auto-PR off (the default), each actionable incident produces a Markdown report with the
root cause, the **tested diff**, the smoke result, and the agent's narrative. Flip
`AUTO_PR_ENABLED=true` (plus a code host + token) for the full self-healing loop.

## Operate it (ESSENCE §7)

```bash
python -m watchdog.ops mute <incident_fingerprint>   # suppress a benign pattern
python -m watchdog.ops rerun <incident_id>           # re-attempt a fix (bypasses the gate)
python -m watchdog.ops backfill <hours>              # replay recent history (single-flighted)
```

## Develop & test

```bash
python -m pytest tests -q       # the watchdog's own suite — no network, no model, no tokens
python -m pytest app/tests -q   # the smoke command the gate runs
```

The default test run touches no network, model, or live agent and finishes in ~1s
(ESSENCE §14). The sandbox + smoke gate is exercised for real but token-free in
`tests/test_fix_path.py`.

## Configuration

All via the environment (see [`config.py`](config.py)). The load-bearing ones:
`LOG_STORE_URL`, `RULES`, `ANTHROPIC_API_KEY`, `DB_PATH`, `REPO_ROOT`, `SMOKE_COMMAND`,
`AUTO_PR_ENABLED`, `CODE_HOST`/`GITHUB_REPO`/`CODE_HOST_TOKEN`, `REVIEW_BRANCH`, `NOTIFIER`,
and the budgets/floors from Appendix H. Boot fails fast if a required secret is missing.
