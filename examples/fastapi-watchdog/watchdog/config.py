"""Configuration & boot invariants (ESSENCE §17, Appendix H, Appendix I).

All config comes from the environment, nothing baked in. ``Config.from_env`` reads it;
``validate_boot`` fails loudly at startup if a required secret/permission is missing
(ESSENCE §14: "a missing credential for the active model fails loudly at startup;
auto-PR on without a code-host token fails at startup").
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Rule:
    """A named query that selects the lines worth watching."""
    name: str
    query: str


@dataclass
class Config:
    # rules to watch (one poll loop per rule)
    rules: list[Rule] = field(default_factory=list)

    # log store
    log_store_url: str = "http://localhost:3100"

    # datastore (default: SQLite — see DECISIONS.md)
    db_path: str = "watchdog_data/watchdog.db"

    # models (provider-agnostic behind an abstraction; default Anthropic Claude)
    triage_model: str = "claude-opus-4-8"
    coding_agent_model: str = "claude-opus-4-8"
    anthropic_api_key: str = ""

    # coding-agent CLI (headless, inside the service image)
    coding_agent_cmd: str = "claude"

    # code host (default: none → auto-PR off, diff attached to report)
    code_host: str = "none"  # "none" | "github"
    github_repo: str = ""  # "owner/repo"
    code_host_token: str = ""
    prod_branch: str = "main"
    review_branch: str = "integration"

    # notifier (default: file sink)
    notifier: str = "file"  # "file" | "smtp"
    reports_dir: str = "watchdog_data/reports"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    notify_from: str = "watchdog@localhost"
    notify_to: str = ""

    # sandbox
    repo_root: str = "."
    smoke_command: str = "python -m pytest app/tests -q"

    # gate
    auto_pr_enabled: bool = False  # ship with auto-PR OFF first (ESSENCE §9)
    strict_pr_gate: bool = False
    confidence_floor: str = "medium"  # via is_actionable

    # cadence & budgets (Appendix H defaults)
    poll_interval_s: int = 60
    time_bucket_s: int = 86_400  # 1 day
    active_window_s: int = 3_600  # 1 hour
    max_candidate_lines: int = 200
    max_active_incidents: int = 20
    samples_per_incident: int = 3
    per_line_char_cap: int = 400
    llm_budget_hourly: int = 200
    llm_budget_daily: int = 1500
    agent_turn_budget: int = 100
    agent_wall_clock_s: int = 900
    fix_size_max_lines: int = 30
    fix_size_max_files: int = 2
    log_retention_s: int = 14 * 86_400
    max_backfill_s: int = 2 * 3_600
    cold_backfill_s: int = 0
    max_concurrent_fixes: int = 2
    circuit_breaker_incidents_per_hour: int = 20

    @classmethod
    def from_env(cls) -> "Config":
        rules_raw = _env(
            "RULES",
            '[{"name": "kvstore-errors", "query": "{service=\\"kvstore\\",level=\\"ERROR\\"}"}]',
        )
        rules = [Rule(**r) for r in json.loads(rules_raw)]
        # MODEL_AUTH is the essence's generic name; ANTHROPIC_API_KEY is what the SDK reads.
        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("MODEL_AUTH", "")
        return cls(
            rules=rules,
            log_store_url=_env("LOG_STORE_URL", cls.log_store_url),
            db_path=_env("DB_PATH", cls.db_path),
            triage_model=_env("TRIAGE_MODEL", cls.triage_model),
            coding_agent_model=_env("CODING_AGENT_MODEL", cls.coding_agent_model),
            anthropic_api_key=api_key,
            coding_agent_cmd=_env("CODING_AGENT_CMD", cls.coding_agent_cmd),
            code_host=_env("CODE_HOST", cls.code_host),
            github_repo=_env("GITHUB_REPO", cls.github_repo),
            code_host_token=os.environ.get("CODE_HOST_TOKEN", os.environ.get("GITHUB_TOKEN", "")),
            prod_branch=_env("PROD_BRANCH", cls.prod_branch),
            review_branch=_env("REVIEW_BRANCH", cls.review_branch),
            notifier=_env("NOTIFIER", cls.notifier),
            reports_dir=_env("REPORTS_DIR", cls.reports_dir),
            smtp_host=_env("SMTP_HOST", cls.smtp_host),
            smtp_port=_env_int("SMTP_PORT", cls.smtp_port),
            smtp_user=_env("SMTP_USER", cls.smtp_user),
            smtp_password=os.environ.get("SMTP_PASSWORD", ""),
            notify_from=_env("NOTIFY_FROM", cls.notify_from),
            notify_to=_env("NOTIFY_TO", cls.notify_to),
            repo_root=_env("REPO_ROOT", cls.repo_root),
            smoke_command=_env("SMOKE_COMMAND", cls.smoke_command),
            auto_pr_enabled=_env_bool("AUTO_PR_ENABLED", cls.auto_pr_enabled),
            strict_pr_gate=_env_bool("STRICT_PR_GATE", cls.strict_pr_gate),
            confidence_floor=_env("CONFIDENCE_FLOOR", cls.confidence_floor),
            poll_interval_s=_env_int("POLL_INTERVAL_S", cls.poll_interval_s),
            time_bucket_s=_env_int("TIME_BUCKET_S", cls.time_bucket_s),
            active_window_s=_env_int("ACTIVE_WINDOW_S", cls.active_window_s),
            max_candidate_lines=_env_int("MAX_CANDIDATE_LINES", cls.max_candidate_lines),
            max_active_incidents=_env_int("MAX_ACTIVE_INCIDENTS", cls.max_active_incidents),
            samples_per_incident=_env_int("SAMPLES_PER_INCIDENT", cls.samples_per_incident),
            per_line_char_cap=_env_int("PER_LINE_CHAR_CAP", cls.per_line_char_cap),
            llm_budget_hourly=_env_int("LLM_BUDGET_HOURLY", cls.llm_budget_hourly),
            llm_budget_daily=_env_int("LLM_BUDGET_DAILY", cls.llm_budget_daily),
            agent_turn_budget=_env_int("AGENT_TURN_BUDGET", cls.agent_turn_budget),
            agent_wall_clock_s=_env_int("AGENT_WALL_CLOCK_S", cls.agent_wall_clock_s),
            fix_size_max_lines=_env_int("FIX_SIZE_MAX_LINES", cls.fix_size_max_lines),
            fix_size_max_files=_env_int("FIX_SIZE_MAX_FILES", cls.fix_size_max_files),
            log_retention_s=_env_int("LOG_RETENTION_S", cls.log_retention_s),
            max_backfill_s=_env_int("MAX_BACKFILL_S", cls.max_backfill_s),
            cold_backfill_s=_env_int("COLD_BACKFILL_S", cls.cold_backfill_s),
            max_concurrent_fixes=_env_int("MAX_CONCURRENT_FIXES", cls.max_concurrent_fixes),
            circuit_breaker_incidents_per_hour=_env_int(
                "CIRCUIT_BREAKER_INCIDENTS_PER_HOUR", cls.circuit_breaker_incidents_per_hour
            ),
        )


class BootError(RuntimeError):
    """Raised when a required secret/permission is missing — fail fast at startup."""


def validate_boot(cfg: Config) -> None:
    """Fail loudly if the configuration can't possibly work (ESSENCE §14 boot invariants)."""
    problems: list[str] = []

    if not cfg.rules:
        problems.append("no RULES configured — nothing to watch")

    # The triage model and coding agent are inherently LLM-backed; without a key they 401.
    if not cfg.anthropic_api_key:
        problems.append(
            "no ANTHROPIC_API_KEY / MODEL_AUTH set — the triage model and coding agent need it"
        )

    # auto-PR on without a code-host token is a misconfiguration that would only surface
    # at the first incident — catch it now.
    if cfg.auto_pr_enabled:
        if cfg.code_host == "none":
            problems.append("AUTO_PR_ENABLED but CODE_HOST=none — nothing can open a PR")
        elif cfg.code_host == "github" and not (cfg.github_repo and cfg.code_host_token):
            problems.append("AUTO_PR_ENABLED with CODE_HOST=github but GITHUB_REPO / token missing")

    if cfg.notifier == "smtp" and not cfg.smtp_host:
        problems.append("NOTIFIER=smtp but SMTP_HOST is empty")

    if problems:
        raise BootError("; ".join(problems))
