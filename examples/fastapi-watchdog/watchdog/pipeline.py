"""The pipeline — stages A–H driven by the poll loop (ESSENCE §4).

One poll runs A–D synchronously; the fix attempt (E–H) runs in the background under a
concurrency cap. The datastore is the source of truth, so a restart re-processes at most
one window with no double-counting.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from . import status as st
from .agent import CodingAgent
from .budget import LLMBudget
from .codehost import CodeHost
from .config import Config
from .fingerprint import bot_branch_name, incident_fingerprint
from .locks import FingerprintLocks
from .logstore import LogStore
from .models import Grouping, Incident
from .notifier import Notifier, report_from_incident
from .remedy import (
    COMPLEMENTARY,
    DUPLICATE,
    NEW,
    SUPERSEDE,
    RemedyAdjudicator,
    remedy_dedup,
)
from .sandbox import LocalGitSandbox
from .store import Datastore
from .triage import TriageModel


@dataclass
class PollResult:
    rule: str
    ingested: int
    candidates: int
    clustering_calls: int
    incidents_created: int
    incidents_linked: int
    noops: int
    fixes_launched: int
    hallucinations: dict
    skipped_no_candidates: bool = False
    skipped_budget: bool = False


class Pipeline:
    def __init__(
        self,
        cfg: Config,
        *,
        store: Datastore,
        log_store: LogStore,
        triage: TriageModel,
        coding_agent: CodingAgent,
        code_host: CodeHost,
        notifier: Notifier,
        budget: LLMBudget,
        adjudicator: Optional[RemedyAdjudicator] = None,
        now_fn: Callable[[], float] = time.time,
        run_fixes_async: bool = True,
    ) -> None:
        self.cfg = cfg
        self.store = store
        self.log_store = log_store
        self.triage = triage
        self.coding_agent = coding_agent
        self.code_host = code_host
        self.notifier = notifier
        self.budget = budget
        self.adjudicator = adjudicator
        self._now = now_fn
        self.run_fixes_async = run_fixes_async
        self._locks = FingerprintLocks()
        self._fix_sem = threading.Semaphore(cfg.max_concurrent_fixes)
        self._inflight: list[threading.Thread] = []
        # circuit breaker accounting
        self._fix_launch_times: list[float] = []

    # --- (A)-(D): one synchronous poll ---------------------------------------------

    def poll(self, rule_name: str, query: str, since: float, until: float) -> PollResult:
        result = PollResult(rule_name, 0, 0, 0, 0, 0, 0, 0,
                            {"unknown_line_id": 0, "unknown_incident_id": 0, "empty_line_ids": 0})

        # (A) Ingest + dedup.
        lines = self.log_store.fetch(query, since, until)
        from .fingerprint import line_fingerprint
        batch = [(line_fingerprint(l.text), l) for l in lines]
        if not batch:
            result.skipped_no_candidates = True
            return result  # zero new lines → stop, no downstream LLM
        result.ingested = self.store.ingest(rule_name, batch)

        # (B) Select candidates.
        candidates = self.store.candidates(rule_name, limit=self.cfg.max_candidate_lines)
        result.candidates = len(candidates)
        if not candidates:
            result.skipped_no_candidates = True
            return result
        actives = self.store.active_incidents(
            self._now(), self.cfg.active_window_s,
            limit=self.cfg.max_active_incidents, samples=self.cfg.samples_per_incident,
        )

        # (C) Cluster — one triage call, budget-gated.
        if not self.budget.try_charge():
            result.skipped_budget = True
            return result  # candidates remain candidates; retried next poll
        result.clustering_calls = 1
        groupings, dropped = self.triage.cluster(candidates, actives)
        for k, v in dropped.items():
            result.hallucinations[k] = result.hallucinations.get(k, 0) + v

        # (D) Dispatch.
        cand_by_id = {c.id: c for c in candidates}
        claimed: set[int] = set()
        to_fix: list[int] = []
        for g in groupings:
            outcome = self._dispatch_one(g, cand_by_id)
            claimed.update(g.line_ids)
            if outcome == "created":
                result.incidents_created += 1
            elif outcome == "linked":
                result.incidents_linked += 1
            elif outcome == "noop":
                result.noops += 1
            if isinstance(outcome, tuple) and outcome[0] == "fix":
                result.incidents_created += 1
                to_fix.append(outcome[1])

        # Lines no grouping claimed → stamp considered so they don't recur forever.
        orphans = [c.id for c in candidates if c.id not in claimed]
        self.store.mark_considered(orphans, self._now())

        # Launch fix attempts (background, concurrency-capped).
        for incident_id in to_fix:
            if self._circuit_open():
                break
            self._launch_fix(incident_id)
            result.fixes_launched += 1
        return result

    def _dispatch_one(self, g: Grouping, cand_by_id: dict):
        now = self._now()
        line_fps = self.store.line_fingerprints_for(g.line_ids)
        ifp = incident_fingerprint(line_fps)
        add_occ = sum(cand_by_id[i].occurrences for i in g.line_ids if i in cand_by_id)

        with self._locks.lock(ifp):
            # Benign short-circuit.
            if g.severity == "noop" and g.is_known_noop:
                self.store.record_noop(ifp, g.noop_reason or "", now)
                self.store.attach_lines(g.line_ids, -1, now)  # mark considered, no incident
                return "noop"
            if self.store.is_known_noop(ifp):
                self.store.attach_lines(g.line_ids, -1, now)
                return "noop"

            # Link to an existing active incident.
            if g.is_link:
                target = g.existing_incident_id
                if self.store.incident_is_active(target, now, self.cfg.active_window_s):
                    self.store.bump_incident(target, add_occ, now)
                    self.store.attach_lines(g.line_ids, target, now)
                    return "linked"  # recurrence of a known thing → no fix, no alert
                # aged out between snapshot and now → re-emergence = fresh ticket (fall through)

            # New: safety-net lookup defends races.
            existing = self.store.find_active_incident(ifp, now, self.cfg.active_window_s)
            if existing is not None:
                self.store.bump_incident(existing, add_occ, now)
                self.store.attach_lines(g.line_ids, existing, now)
                return "linked"

            # Create the incident.
            samples = [cand_by_id[i].text for i in g.line_ids if i in cand_by_id][
                : self.cfg.samples_per_incident
            ]
            inc = Incident(
                incident_fingerprint=ifp,
                slug=g.slug or "incident",
                severity=g.severity,
                confidence=g.confidence,
                root_cause=g.root_cause,
                summary=g.summary,
                affected_files=g.affected_files,
                occurrences=add_occ,
                first_seen=now,
                last_seen=now,
                created_at=now,
                sample_lines=samples,
                triage_model=getattr(self.triage, "model", "fake-triage"),
            )
            incident_id = self.store.create_incident(inc)
            self.store.attach_lines(g.line_ids, incident_id, now)

            # Gate: attempt a fix only for actionable incidents.
            if st.is_actionable(g.severity, g.confidence):
                return ("fix", incident_id)
            self.store.update_incident_fix(incident_id, status=st.SKIPPED)
            return "created"

    # --- (E)-(H): the background fix attempt --------------------------------------

    def _launch_fix(self, incident_id: int) -> None:
        self._fix_launch_times.append(self._now())
        if not self.run_fixes_async:
            self.run_fix(incident_id)
            return
        t = threading.Thread(target=self.run_fix, args=(incident_id,), daemon=True)
        self._inflight.append(t)
        t.start()

    def run_fix(self, incident_id: int) -> None:
        with self._fix_sem:
            self._run_fix_inner(incident_id)

    def _run_fix_inner(self, incident_id: int) -> None:
        inc = self.store.get_incident(incident_id)
        if inc is None:
            return
        inc.coding_agent_model = getattr(self.coding_agent, "model", "fake-agent")
        branch = bot_branch_name(inc.slug, inc.incident_fingerprint)
        sandbox = LocalGitSandbox(
            self.cfg.repo_root,
            smoke_command=self.cfg.smoke_command,
            branch=branch,
            prod_branch=self.cfg.prod_branch,
        )
        try:
            sandbox.materialize()
            fix = self.coding_agent.attempt_fix(inc, sandbox)
        finally:
            sandbox.cleanup()

        # Persist the fix outcome on the incident.
        self.store.update_incident_fix(
            incident_id,
            status=fix.status,
            diff=fix.diff,
            smoke_result=fix.smoke_passed,
            narrative=fix.narrative,
            agent_log=fix.agent_log,
            tokens_in=fix.tokens_in,
            tokens_out=fix.tokens_out,
            turns=fix.turns,
            wall_clock_s=fix.wall_clock_s,
            coding_agent_model=inc.coding_agent_model,
        )

        pr_url, pr_skip_reason, dedup_verdict, dedup_action = self._deliver_pr(inc, fix, branch)
        self.store.update_incident_fix(
            incident_id,
            pr_url=pr_url, pr_skip_reason=pr_skip_reason,
            dedup_verdict=dedup_verdict, dedup_action=dedup_action,
        )

        # (H) Send exactly one report.
        inc = self.store.get_incident(incident_id)
        self._send_report(inc)

    def _deliver_pr(self, inc: Incident, fix, branch: str):
        """Returns (pr_url, pr_skip_reason, dedup_verdict, dedup_action)."""
        open_pr = st.should_open_pr(
            severity=inc.severity, confidence=inc.confidence, status=fix.status,
            auto_pr_enabled=self.cfg.auto_pr_enabled, strict=self.cfg.strict_pr_gate,
        )
        if not open_pr:
            if not self.cfg.auto_pr_enabled:
                reason = "auto-PR disabled (diff attached to report)"
            elif fix.status == st.DEFERRED:
                reason = "fix deferred (too big to do safely)"
            elif fix.status != st.SUCCEEDED:
                reason = f"fix did not succeed (status={fix.status})"
            else:
                reason = "did not meet PR gate"
            return None, reason, None, None

        # (G) Remedy dedup — fails open to NEW.
        decision = remedy_dedup(
            fix.diff, self.code_host,
            base_branch=self.cfg.review_branch,
            adjudicator=self.adjudicator,
        )
        title = f"{inc.slug}: {inc.summary[:60]}"
        body = _pr_body(inc, fix)

        try:
            if decision.action == NEW:
                url = self.code_host.open_pr(
                    branch=branch, base=self.cfg.review_branch, title=title, body=body, diff=fix.diff
                )
                return url, None, decision.verdict, NEW
            if decision.action == DUPLICATE:
                self.code_host.comment(
                    decision.target_pr, f"watchdog: incident '{inc.slug}' has the same fix as this PR."
                )
                return decision.target_url, "duplicate of an existing PR (linked)", decision.verdict, DUPLICATE
            if decision.action == SUPERSEDE:
                # Post a self-contained merge brief on the old PR; never force-push over it.
                self.code_host.comment(
                    decision.target_pr,
                    f"watchdog: a more complete fix for '{inc.slug}' is in {branch}.\n\n{body}",
                )
                url = self.code_host.open_pr(
                    branch=branch, base=self.cfg.review_branch, title=title, body=body, diff=fix.diff
                )
                return url, None, decision.verdict, SUPERSEDE
            if decision.action == COMPLEMENTARY:
                url = self.code_host.open_pr(
                    branch=branch, base=self.cfg.review_branch, title=title, body=body, diff=fix.diff
                )
                if decision.target_pr is not None:
                    self.code_host.comment(decision.target_pr, f"watchdog: complementary fix opened: {url}")
                return url, None, decision.verdict, COMPLEMENTARY
        except Exception as exc:  # noqa: BLE001 - delivery failures are reported, not fatal
            return None, f"PR delivery error: {exc}", decision.verdict, decision.action
        return None, "unknown dedup action", decision.verdict, decision.action

    def _send_report(self, inc: Incident) -> None:
        report = report_from_incident(inc)
        for attempt in range(3):
            outcome = self.notifier.send(report)
            if outcome.get("delivered"):
                self.store.update_incident_fix(inc.id, report_sent_at=self._now())
                return
            time.sleep(0)  # transient retry (no real backoff in tests)
        self.store.update_incident_fix(
            inc.id,
            delivery_failed_at=self._now(),
            delivery_failure_reason=outcome.get("failure_reason", "unknown"),
        )

    # --- circuit breaker (§8) ------------------------------------------------------

    def _circuit_open(self) -> bool:
        now = self._now()
        self._fix_launch_times = [t for t in self._fix_launch_times if t >= now - 3600]
        return len(self._fix_launch_times) > self.cfg.circuit_breaker_incidents_per_hour

    def wait_for_fixes(self, timeout: Optional[float] = None) -> None:
        for t in list(self._inflight):
            t.join(timeout)
        self._inflight = [t for t in self._inflight if t.is_alive()]


def _pr_body(inc: Incident, fix) -> str:
    return (
        f"**watchdog drafted this fix for incident `{inc.slug}`.**\n\n"
        f"- Severity: {inc.severity} · Confidence: {inc.confidence}\n"
        f"- Root cause: {inc.root_cause}\n"
        f"- Smoke gate: {'passed' if fix.smoke_passed else 'n/a'}\n\n"
        f"{inc.summary}\n\n"
        f"_Automation proposes; a human merges. Review before merging._"
    )
