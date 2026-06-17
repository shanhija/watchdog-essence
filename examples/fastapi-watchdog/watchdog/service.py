"""The resident service — the main loop and wiring (ESSENCE §4, §7, Appendix I).

A long-running process: one poll loop per rule, plus periodic jobs, started once and run
forever. A single bad poll never kills the process; the resume points + dedup table make
a supervisor restart free. Config & secrets come entirely from the environment.
"""
from __future__ import annotations

import json
import logging
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

from . import jobs
from .agent import ClaudeCliCodingAgent
from .budget import LLMBudget
from .codehost import GitHubCodeHost, NullCodeHost
from .config import Config, validate_boot
from .logstore import LokiLogStore
from .notifier import FileNotifier, SmtpNotifier
from .pipeline import Pipeline
from .remedy import AnthropicRemedyAdjudicator
from .store import Datastore
from .triage import AnthropicTriageModel

log = logging.getLogger("watchdog")


def build_pipeline(cfg: Config) -> tuple[Pipeline, Datastore]:
    """Wire the concrete ports from config (the dependency-injection seam for tests)."""
    store = Datastore(cfg.db_path, time_bucket_s=cfg.time_bucket_s)
    log_store = LokiLogStore(cfg.log_store_url)
    triage = AnthropicTriageModel(cfg.anthropic_api_key, cfg.triage_model,
                                  per_line_char_cap=cfg.per_line_char_cap)
    coding_agent = ClaudeCliCodingAgent(
        cli_cmd=cfg.coding_agent_cmd, api_key=cfg.anthropic_api_key, model=cfg.coding_agent_model,
        repo=cfg.repo_root, smoke_command=cfg.smoke_command,
        turn_budget=cfg.agent_turn_budget, wall_clock_s=cfg.agent_wall_clock_s,
        max_lines=cfg.fix_size_max_lines, max_files=cfg.fix_size_max_files,
    )
    if cfg.code_host == "github":
        code_host = GitHubCodeHost(cfg.github_repo, cfg.code_host_token)
    else:
        code_host = NullCodeHost()
    if cfg.notifier == "smtp":
        notifier = SmtpNotifier(
            host=cfg.smtp_host, port=cfg.smtp_port, user=cfg.smtp_user,
            password=cfg.smtp_password, sender=cfg.notify_from, recipients=cfg.notify_to,
        )
    else:
        notifier = FileNotifier(cfg.reports_dir)
    budget = LLMBudget(cfg.llm_budget_hourly, cfg.llm_budget_daily)
    adjudicator = (
        AnthropicRemedyAdjudicator(cfg.anthropic_api_key, cfg.triage_model)
        if cfg.anthropic_api_key else None
    )
    pipeline = Pipeline(
        cfg, store=store, log_store=log_store, triage=triage, coding_agent=coding_agent,
        code_host=code_host, notifier=notifier, budget=budget, adjudicator=adjudicator,
    )
    return pipeline, store


class Service:
    def __init__(self, cfg: Config, pipeline: Pipeline, store: Datastore) -> None:
        self.cfg = cfg
        self.pipeline = pipeline
        self.store = store
        self._stop = threading.Event()
        self.last_successful_poll: dict[str, float] = {}
        self._last_job_run: dict[str, float] = {}

    # --- resume logic (ESSENCE §12) -----------------------------------------------

    def initial_since(self, rule: str, now: float) -> float:
        saved = self.store.load_resume(rule)
        if saved is None:
            # Cold start: begin at now, or replay a configured backfill window.
            since = now - self.cfg.cold_backfill_s if self.cfg.cold_backfill_s else now
        else:
            # Warm restart: bridge from saved to now, capped at the max backfill window.
            since = max(saved, now - self.cfg.max_backfill_s)
        self.store.save_resume(rule, since)
        return since

    def poll_once(self, rule, now: float) -> None:
        since = self.store.load_resume(rule.name) or self.initial_since(rule.name, now)
        until = now
        try:
            result = self.pipeline.poll(rule.name, rule.query, since, until)
            # Advance the resume point ONLY on a successful poll.
            self.store.save_resume(rule.name, until)
            self.last_successful_poll[rule.name] = now
            log.info("poll %s: %s", rule.name, result)
        except Exception:  # noqa: BLE001 - a bad poll must never kill the process
            log.exception("poll failed for rule %s; not advancing resume point", rule.name)

    # --- periodic jobs (ESSENCE §7) -----------------------------------------------

    def _due(self, name: str, now: float, interval: float) -> bool:
        last = self._last_job_run.get(name, 0.0)
        if now - last >= interval:
            self._last_job_run[name] = now
            return True
        return False

    def run_periodic(self, now: float) -> None:
        if self._due("benign_digest", now, 86_400):
            jobs.benign_digest(self.store, self.pipeline.notifier, now)
        if self._due("backlog_digest", now + 3_600, 86_400):  # slightly offset
            jobs.backlog_digest(self.store, self.pipeline.notifier, now, self.cfg.active_window_s)
        if self._due("retention", now, 86_400):
            jobs.retention_sweep(self.store, now, self.cfg.log_retention_s)

    # --- the loop -----------------------------------------------------------------

    def run(self) -> None:
        now = time.time()
        for rule in self.cfg.rules:
            self.initial_since(rule.name, now)
        log.info("watchdog started; watching %d rule(s)", len(self.cfg.rules))
        while not self._stop.is_set():
            now = time.time()
            for rule in self.cfg.rules:
                if self._stop.is_set():
                    break
                self.poll_once(rule, now)
            self.run_periodic(now)
            self._stop.wait(self.cfg.poll_interval_s)
        # Graceful drain on shutdown.
        log.info("shutdown: waiting for in-flight fix attempts")
        self.pipeline.wait_for_fixes(timeout=self.cfg.agent_wall_clock_s)
        self.store.close()

    def stop(self) -> None:
        self._stop.set()

    def metrics(self) -> dict:
        return {
            "last_successful_poll": self.last_successful_poll,
            **self.store.counts(),
        }


def _start_health_server(service: Service, port: int = 8080) -> Optional[HTTPServer]:
    svc = service

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence default logging
            pass

        def do_GET(self):
            if self.path == "/metrics":
                body = json.dumps(svc.metrics()).encode()
            elif self.path in ("/healthz", "/readyz", "/"):
                body = json.dumps({"ok": True}).encode()
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    try:
        server = HTTPServer(("0.0.0.0", port), Handler)
    except OSError:
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    cfg = Config.from_env()
    validate_boot(cfg)  # fail fast if a required secret/permission is missing
    pipeline, store = build_pipeline(cfg)
    service = Service(cfg, pipeline, store)
    _start_health_server(service)

    def _handle_sigterm(signum, frame):
        log.info("received signal %s; stopping", signum)
        service.stop()

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)
    service.run()


if __name__ == "__main__":
    main()
