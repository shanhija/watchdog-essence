"""Periodic jobs beyond the poll loop (ESSENCE §7).

Digests are rendered as pure functions (testable) and sent through the notifier with a
stable per-day id so a double-send de-dups at the recipient. Retention sweeps log lines
only — incidents are never deleted.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from .models import Report
from .notifier import Notifier
from .store import Datastore


def _day_id(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")


def render_noop_digest(rows: list, day: str) -> str:
    lines = [f"# Benign (noop) patterns seen — {day}", ""]
    for r in rows:
        lines.append(f"- `{r['incident_fingerprint'][:8]}` ×{r['occurrences']}: {r['reason']}")
    return "\n".join(lines)


def render_backlog_digest(incidents: list, day: str) -> str:
    lines = [f"# Backlog — incidents active in the last window ({day})", ""]
    for inc in incidents:
        lines.append(f"- **{inc.severity}** `{inc.slug}` ×{inc.occurrences} "
                     f"(status={inc.status or 'pending'})")
    return "\n".join(lines)


def _digest_report(slug: str, body: str, day: str) -> Report:
    # Reuse the Report shape so digests flow through the same notifier; stable id per day.
    incident_id = abs(hash((slug, day))) % 1_000_000
    return Report(
        incident_id=incident_id, slug=f"{slug}-{day}", severity="low", confidence="high",
        summary=body, root_cause="", sample_lines=[], status="digest", diff="",
        smoke_passed=None, narrative="", pr_url=None, pr_skip_reason=None,
        triage_model="", coding_agent_model="", dedup_verdict=None,
    )


def benign_digest(store: Datastore, notifier: Notifier, now: float) -> bool:
    """Once a day: summarize benign incidents in the last 24h. Skip the send if empty."""
    rows = store.noop_digest(now - 86_400)
    if not rows:
        return False  # no "nothing to report" noise
    day = _day_id(now)
    notifier.send(_digest_report("benign-digest", render_noop_digest(rows, day), day))
    return True


def backlog_digest(store: Datastore, notifier: Notifier, now: float, active_s: int) -> bool:
    """Once a day: list incidents still in their active window (the stuff to deal with)."""
    incidents = store.backlog_digest(now, active_s)
    if not incidents:
        return False
    day = _day_id(now)
    notifier.send(_digest_report("backlog-digest", render_backlog_digest(incidents, day), day))
    return True


def retention_sweep(store: Datastore, now: float, retention_s: int) -> int:
    """Hard-delete log lines older than the retention window. Never deletes incidents."""
    return store.sweep_log_lines(now - retention_s)
