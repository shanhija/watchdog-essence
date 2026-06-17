# Watchdog — role mapping & decisions

This service was grown from `ESSENCE.md` against the `kvstore` app in this repository. The
essence describes **roles**; this file records how each role was mapped to *this*
environment, and — because this build ran non-interactively — every place the essence says
"ask the user", written out as a question with the default that was chosen and why.

## Role mapping (ESSENCE §3, §17)

| Role | Mapped to | Where |
|---|---|---|
| ***Log store*** | **Loki** (already in the compose stack), `query_range` API | `logstore.py` (`LokiLogStore`) |
| **Rule** | `{service="kvstore",level="ERROR"}` | `config.py` (env `RULES`) |
| ***Datastore*** | **SQLite** (file in a Docker volume) | `store.py` |
| ***Triage model*** | **Anthropic Claude** (`claude-opus-4-8`), forced tool-call | `triage.py` |
| ***Coding agent*** | **Claude Code CLI**, headless inside the image | `agent.py` |
| ***Sandbox*** | fresh tree copy + `git init` in a tempdir, per fix attempt | `sandbox.py` |
| ***Code host*** | **none by default** (auto-PR off); GitHub adapter available | `codehost.py` |
| ***Notifier*** | **file sink** by default; SMTP adapter available | `notifier.py` |
| **prod / review branch** | `main` / `integration` | `config.py` |
| **Smoke command** | `python -m pytest app/tests -q` | `config.py` |
| **Deploy substrate** | another service in `docker-compose.yml` | `Dockerfile`, `docker-compose.yml` |

## Gaps the essence says to ask about — questions + chosen defaults

The essence (§2.12, §17, Appendix I) says: where a role is missing or a choice is ambiguous,
ask the user with concrete suggestions. This run was non-interactive, so each is stated here
with the default chosen. **All are overridable by environment variable** — see `config.py`.

1. **Which datastore?** (no datastore exists in the env)
   Options: SQLite (file) · Postgres · a queried table.
   **Default chosen: SQLite** (`DB_PATH`, default `/data/watchdog.db`). It has
   `INSERT … ON CONFLICT` (the only datastore feature the essence requires) and ships with
   Python, so it adds no service to the compose stack. Swap by replacing `Datastore`.

2. **Where should pull requests go?** (no code host is wired for automation)
   Options: GitHub (give repo + token) · write patch files to a directory · attach the diff
   to the report only.
   **Default chosen: auto-PR OFF** (`AUTO_PR_ENABLED=false`) — the diff is attached to the
   report (ESSENCE §9's recommended starting posture: full value, zero branch risk). To turn
   it on, set `CODE_HOST=github`, `GITHUB_REPO`, `CODE_HOST_TOKEN`, `AUTO_PR_ENABLED=true`
   (boot validation enforces that the token is present — ESSENCE §14).

3. **How should reports be delivered?** (no notifier exists)
   Options: email (SMTP) · chat webhook · a file/directory sink.
   **Default chosen: file sink** (`NOTIFIER=file`, `REPORTS_DIR=/data/reports`) — one
   Markdown file per incident plus the agent log as a sibling attachment. Set `NOTIFIER=smtp`
   with `SMTP_*` / `NOTIFY_TO` to email instead.

4. **Where should the service run?** (deploy target)
   The watched app is deployed via Docker Compose, so — per Appendix I ("join it there") —
   **the watchdog is added as another service in `docker-compose.yml`**, reaching Loki over
   the network and provisioning its own sandboxes. (A k8s Deployment / systemd unit would be
   the equivalent in those substrates.)

5. **The repo is not itself a git repo.** The sandbox therefore copies the source tree into a
   tempdir and `git init`s it to get a pristine, isolated, diffable base per fix attempt
   (ESSENCE §4E's non-negotiables: *pristine + isolated*, with the app's runtime + test deps
   present). Set `PROD_BRANCH` / `REVIEW_BRANCH` if your real repo differs.

6. **LLM provider / models.** Defaulted to **Anthropic Claude `claude-opus-4-8`** for both the
   triage model and the coding agent (`TRIAGE_MODEL`, `CODING_AGENT_MODEL`). Both AI roles
   sit behind a thin abstraction (ESSENCE §6, lesson #13) so a different capable model can be
   swapped in.

## Build status (what is wired vs. stubbed)

- **Fully implemented and tested offline:** fingerprinting (all three keys), ingest/dedup,
  candidate selection, the dispatch state machine (link/create/benign/safety-net/re-emergence),
  the gate, status taxonomy, remedy-dedup cascade, report rendering, budgets, resume/backfill
  logic, retention + digests, boot invariants. 70 unit/functional tests; the default run
  touches no network, model, or live agent.
- **Real but require live credentials/CLI at runtime:** the Anthropic triage call, the Claude
  Code CLI coding agent, the GitHub code host, SMTP delivery. The **sandbox + smoke gate is
  exercised for real, token-free** in `tests/test_fix_path.py` (a scripted agent applies the
  kvstore `KeyError` fix; the actual `pytest app/tests` smoke command runs and gates it).
- **Known runtime caveat:** the GitHub adapter opens the PR over the API but assumes the bot
  branch is pushed to the remote; a compare-and-swap `git push` to a real remote is not wired
  (the default path is auto-PR off, so this isn't on the critical path). It's marked in
  `codehost.py`.

## Phased rollout (ESSENCE §16)

Start with auto-PR off (current default): you immediately stop missing errors and get tested
draft fixes in `REPORTS_DIR`. When you trust it, wire a code host + token and flip
`AUTO_PR_ENABLED=true` to get the full self-healing loop into your review branch.
