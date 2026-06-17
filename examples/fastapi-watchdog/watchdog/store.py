"""Datastore — the source of truth (ESSENCE §5 invariant, §12, Appendix G).

Default implementation: SQLite (see DECISIONS.md). Any datastore with upsert /
ON CONFLICT semantics works; SQLite has ``INSERT ... ON CONFLICT`` and ships with
Python, so it needs no extra service in the compose stack.

The four logical tables: log_lines (dedup table), incidents, known_noop_patterns,
tailer_progress. Restart-safety falls out of this for free.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Optional

from .models import ActiveIncident, Candidate, Incident, LogLine

_SCHEMA = """
CREATE TABLE IF NOT EXISTS log_lines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    line_fingerprint TEXT NOT NULL,
    time_bucket     INTEGER NOT NULL,
    rule            TEXT NOT NULL,
    text            TEXT NOT NULL,
    labels          TEXT NOT NULL,
    occurrences     INTEGER NOT NULL DEFAULT 1,
    first_seen      REAL NOT NULL,
    last_seen       REAL NOT NULL,
    last_clustered  REAL,
    incident_id     INTEGER,
    UNIQUE(line_fingerprint, time_bucket)
);
CREATE INDEX IF NOT EXISTS ix_log_lines_rule ON log_lines(rule);

CREATE TABLE IF NOT EXISTS incidents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_fingerprint TEXT NOT NULL,
    slug            TEXT NOT NULL,
    severity        TEXT NOT NULL,
    confidence      TEXT NOT NULL,
    root_cause      TEXT NOT NULL DEFAULT '',
    summary         TEXT NOT NULL DEFAULT '',
    affected_files  TEXT NOT NULL DEFAULT '[]',
    occurrences     INTEGER NOT NULL DEFAULT 0,
    first_seen      REAL NOT NULL,
    last_seen       REAL NOT NULL,
    created_at      REAL NOT NULL,
    status          TEXT,
    diff            TEXT,
    pr_url          TEXT,
    dedup_action    TEXT,
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    turns           INTEGER,
    wall_clock_s    REAL,
    smoke_result    INTEGER,
    narrative       TEXT,
    agent_log       TEXT,
    pr_skip_reason  TEXT,
    triage_model    TEXT,
    coding_agent_model TEXT,
    dedup_verdict   TEXT,
    sample_lines    TEXT NOT NULL DEFAULT '[]',
    report_sent_at  REAL,
    delivery_failed_at REAL,
    delivery_failure_reason TEXT
);
CREATE INDEX IF NOT EXISTS ix_incidents_fp ON incidents(incident_fingerprint);

CREATE TABLE IF NOT EXISTS known_noop_patterns (
    incident_fingerprint TEXT PRIMARY KEY,
    reason          TEXT NOT NULL DEFAULT '',
    last_seen       REAL NOT NULL,
    occurrences     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tailer_progress (
    rule            TEXT PRIMARY KEY,
    last_processed_at REAL NOT NULL
);
"""


def _bucket(ts: float, bucket_s: int) -> int:
    return int(ts // bucket_s) * bucket_s


class Datastore:
    def __init__(self, db_path: str, *, time_bucket_s: int = 86_400) -> None:
        self.db_path = db_path
        self.time_bucket_s = time_bucket_s
        if db_path != ":memory:":
            parent = os.path.dirname(db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        # check_same_thread=False: the fix attempts run in background threads.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- ingest + dedup (stage A) -------------------------------------------------

    def ingest(self, rule: str, lines: list[tuple[str, LogLine]]) -> int:
        """Upsert each (line_fingerprint, line) by (line_fingerprint, time_bucket).

        On conflict: bump occurrences + advance last_seen. Collapse duplicates *within*
        the batch first (most stores reject two conflicting writes to one key in one
        statement). Returns the number of rows touched.
        """
        if not lines:
            return 0
        # Collapse within-batch duplicates by (fingerprint, bucket).
        collapsed: dict[tuple[str, int], dict] = {}
        for fp, line in lines:
            bucket = _bucket(line.ts, self.time_bucket_s)
            key = (fp, bucket)
            entry = collapsed.get(key)
            if entry is None:
                collapsed[key] = {
                    "fp": fp,
                    "bucket": bucket,
                    "text": line.text,
                    "labels": line.labels,
                    "count": 1,
                    "first": line.ts,
                    "last": line.ts,
                }
            else:
                entry["count"] += 1
                entry["first"] = min(entry["first"], line.ts)
                entry["last"] = max(entry["last"], line.ts)
        with self._lock:
            for e in collapsed.values():
                self._conn.execute(
                    """
                    INSERT INTO log_lines
                        (line_fingerprint, time_bucket, rule, text, labels,
                         occurrences, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(line_fingerprint, time_bucket) DO UPDATE SET
                        occurrences = occurrences + excluded.occurrences,
                        last_seen = MAX(last_seen, excluded.last_seen)
                    """,
                    (
                        e["fp"], e["bucket"], rule, e["text"][:4000],
                        json.dumps(e["labels"]), e["count"], e["first"], e["last"],
                    ),
                )
            self._conn.commit()
        return len(collapsed)

    # --- select candidates (stage B) ----------------------------------------------

    def candidates(self, rule: str, *, limit: int = 200) -> list[Candidate]:
        rows = self._conn.execute(
            """
            SELECT id, line_fingerprint, text, labels, occurrences
            FROM log_lines
            WHERE rule = ?
              AND (last_clustered IS NULL OR last_seen > last_clustered)
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            (rule, limit),
        ).fetchall()
        return [
            Candidate(
                id=r["id"],
                line_fingerprint=r["line_fingerprint"],
                text=r["text"],
                labels=json.loads(r["labels"]),
                occurrences=r["occurrences"],
            )
            for r in rows
        ]

    def line_fingerprints_for(self, line_ids: list[int]) -> list[str]:
        if not line_ids:
            return []
        q = ",".join("?" * len(line_ids))
        rows = self._conn.execute(
            f"SELECT line_fingerprint FROM log_lines WHERE id IN ({q})", line_ids
        ).fetchall()
        return [r["line_fingerprint"] for r in rows]

    def active_incidents(self, now: float, active_s: int, *, limit: int = 20,
                         samples: int = 3) -> list[ActiveIncident]:
        rows = self._conn.execute(
            """
            SELECT id, slug, severity, summary
            FROM incidents
            WHERE last_seen >= ? AND severity != 'noop'
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            (now - active_s, limit),
        ).fetchall()
        out: list[ActiveIncident] = []
        for r in rows:
            sample_rows = self._conn.execute(
                "SELECT text FROM log_lines WHERE incident_id = ? ORDER BY last_seen DESC LIMIT ?",
                (r["id"], samples),
            ).fetchall()
            out.append(
                ActiveIncident(
                    id=r["id"],
                    slug=r["slug"],
                    severity=r["severity"],
                    summary=r["summary"],
                    samples=[s["text"] for s in sample_rows],
                )
            )
        return out

    # --- dispatch (stage D) -------------------------------------------------------

    def find_active_incident(self, ifp: str, now: float, active_s: int) -> Optional[int]:
        row = self._conn.execute(
            """
            SELECT id FROM incidents
            WHERE incident_fingerprint = ? AND last_seen >= ?
            ORDER BY last_seen DESC LIMIT 1
            """,
            (ifp, now - active_s),
        ).fetchone()
        return row["id"] if row else None

    def incident_is_active(self, incident_id: int, now: float, active_s: int) -> bool:
        row = self._conn.execute(
            "SELECT last_seen FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
        return bool(row) and row["last_seen"] >= now - active_s

    def create_incident(self, inc: Incident) -> int:
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO incidents
                    (incident_fingerprint, slug, severity, confidence, root_cause,
                     summary, affected_files, occurrences, first_seen, last_seen,
                     created_at, status, sample_lines, triage_model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inc.incident_fingerprint, inc.slug, inc.severity, inc.confidence,
                    inc.root_cause, inc.summary, json.dumps(inc.affected_files),
                    inc.occurrences, inc.first_seen, inc.last_seen, inc.created_at,
                    inc.status, json.dumps(inc.sample_lines), inc.triage_model,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def bump_incident(self, incident_id: int, add_occ: int, now: float) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE incidents SET occurrences = occurrences + ?, last_seen = MAX(last_seen, ?) "
                "WHERE id = ?",
                (add_occ, now, incident_id),
            )
            self._conn.commit()

    def update_incident_fix(self, incident_id: int, **fields) -> None:
        if not fields:
            return
        # JSON-encode list fields.
        if "affected_files" in fields and isinstance(fields["affected_files"], list):
            fields["affected_files"] = json.dumps(fields["affected_files"])
        if "sample_lines" in fields and isinstance(fields["sample_lines"], list):
            fields["sample_lines"] = json.dumps(fields["sample_lines"])
        if "smoke_result" in fields and isinstance(fields["smoke_result"], bool):
            fields["smoke_result"] = 1 if fields["smoke_result"] else 0
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._lock:
            self._conn.execute(
                f"UPDATE incidents SET {cols} WHERE id = ?",
                (*fields.values(), incident_id),
            )
            self._conn.commit()

    def get_incident(self, incident_id: int) -> Optional[Incident]:
        row = self._conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        return _row_to_incident(row) if row else None

    def record_noop(self, ifp: str, reason: str, now: float) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO known_noop_patterns (incident_fingerprint, reason, last_seen, occurrences)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(incident_fingerprint) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    occurrences = occurrences + 1,
                    reason = excluded.reason
                """,
                (ifp, reason, now),
            )
            self._conn.commit()

    def is_known_noop(self, ifp: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM known_noop_patterns WHERE incident_fingerprint = ?", (ifp,)
        ).fetchone()
        return row is not None

    def attach_lines(self, line_ids: list[int], incident_id: int, now: float) -> None:
        if not line_ids:
            return
        q = ",".join("?" * len(line_ids))
        with self._lock:
            self._conn.execute(
                f"UPDATE log_lines SET incident_id = ?, last_clustered = ? WHERE id IN ({q})",
                (incident_id, now, *line_ids),
            )
            self._conn.commit()

    def mark_considered(self, line_ids: list[int], now: float) -> None:
        if not line_ids:
            return
        q = ",".join("?" * len(line_ids))
        with self._lock:
            self._conn.execute(
                f"UPDATE log_lines SET last_clustered = ? WHERE id IN ({q})",
                (now, *line_ids),
            )
            self._conn.commit()

    # --- resume points (stage / startup) ------------------------------------------

    def load_resume(self, rule: str) -> Optional[float]:
        row = self._conn.execute(
            "SELECT last_processed_at FROM tailer_progress WHERE rule = ?", (rule,)
        ).fetchone()
        return row["last_processed_at"] if row else None

    def save_resume(self, rule: str, ts: float) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO tailer_progress (rule, last_processed_at) VALUES (?, ?)
                ON CONFLICT(rule) DO UPDATE SET last_processed_at = excluded.last_processed_at
                """,
                (rule, ts),
            )
            self._conn.commit()

    # --- periodic jobs (§7) -------------------------------------------------------

    def sweep_log_lines(self, older_than: float) -> int:
        """Hard-delete log lines older than the retention window. Never deletes incidents."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM log_lines WHERE last_seen < ?", (older_than,))
            self._conn.commit()
            return cur.rowcount

    def noop_digest(self, since: float) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT incident_fingerprint, reason, occurrences, last_seen "
            "FROM known_noop_patterns WHERE last_seen >= ? ORDER BY last_seen DESC",
            (since,),
        ).fetchall()

    def backlog_digest(self, now: float, active_s: int) -> list[Incident]:
        rows = self._conn.execute(
            "SELECT * FROM incidents WHERE last_seen >= ? AND severity != 'noop' "
            "ORDER BY last_seen DESC",
            (now - active_s,),
        ).fetchall()
        return [_row_to_incident(r) for r in rows]

    def counts(self) -> dict[str, int]:
        return {
            "log_lines": self._scalar("SELECT COUNT(*) FROM log_lines"),
            "incidents": self._scalar("SELECT COUNT(*) FROM incidents"),
            "orphan_lines": self._scalar(
                "SELECT COUNT(*) FROM log_lines WHERE incident_id IS NULL AND last_clustered IS NOT NULL"
            ),
            "known_noops": self._scalar("SELECT COUNT(*) FROM known_noop_patterns"),
        }

    def _scalar(self, sql: str) -> int:
        return int(self._conn.execute(sql).fetchone()[0])


def _row_to_incident(row: sqlite3.Row) -> Incident:
    return Incident(
        id=row["id"],
        incident_fingerprint=row["incident_fingerprint"],
        slug=row["slug"],
        severity=row["severity"],
        confidence=row["confidence"],
        root_cause=row["root_cause"],
        summary=row["summary"],
        affected_files=json.loads(row["affected_files"]),
        occurrences=row["occurrences"],
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
        created_at=row["created_at"],
        status=row["status"],
        diff=row["diff"],
        pr_url=row["pr_url"],
        dedup_action=row["dedup_action"],
        tokens_in=row["tokens_in"],
        tokens_out=row["tokens_out"],
        turns=row["turns"],
        wall_clock_s=row["wall_clock_s"],
        smoke_result=None if row["smoke_result"] is None else bool(row["smoke_result"]),
        narrative=row["narrative"],
        agent_log=row["agent_log"],
        pr_skip_reason=row["pr_skip_reason"],
        triage_model=row["triage_model"],
        coding_agent_model=row["coding_agent_model"],
        dedup_verdict=row["dedup_verdict"],
        sample_lines=json.loads(row["sample_lines"]),
        report_sent_at=row["report_sent_at"],
        delivery_failed_at=row["delivery_failed_at"],
        delivery_failure_reason=row["delivery_failure_reason"],
    )
