"""Data shapes that flow through the pipeline (ESSENCE Appendix A)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LogLine:
    """One line from the log store."""
    ts: float  # epoch seconds
    text: str
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class Candidate:
    """A not-yet-clustered dedup row handed to triage."""
    id: int
    line_fingerprint: str
    text: str
    labels: dict[str, str]
    occurrences: int


@dataclass
class Grouping:
    """Triage's per-cluster output (link XOR new).

    existing_incident_id non-null ⇒ link; null ⇒ new (the new-incident fields apply).
    """
    line_ids: list[int]
    existing_incident_id: Optional[int] = None
    slug: str = ""
    severity: str = "low"
    confidence: str = "low"
    root_cause: str = ""
    affected_files: list[str] = field(default_factory=list)
    summary: str = ""
    is_known_noop: bool = False
    noop_reason: Optional[str] = None

    @property
    def is_link(self) -> bool:
        return self.existing_incident_id is not None


@dataclass
class ActiveIncident:
    """The slim view of an active incident surfaced to the triage model."""
    id: int
    slug: str
    severity: str
    summary: str
    samples: list[str]


@dataclass
class Incident:
    """A persisted incident (symptom identity = incident_fingerprint)."""
    id: Optional[int] = None
    incident_fingerprint: str = ""
    slug: str = ""
    severity: str = "low"
    confidence: str = "low"
    root_cause: str = ""
    summary: str = ""
    affected_files: list[str] = field(default_factory=list)
    occurrences: int = 0
    first_seen: float = 0.0
    last_seen: float = 0.0
    created_at: float = 0.0
    # fix-attempt fields
    status: Optional[str] = None
    diff: Optional[str] = None
    pr_url: Optional[str] = None
    dedup_action: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    turns: Optional[int] = None
    wall_clock_s: Optional[float] = None
    smoke_result: Optional[bool] = None
    narrative: Optional[str] = None
    agent_log: Optional[str] = None
    pr_skip_reason: Optional[str] = None
    triage_model: Optional[str] = None
    coding_agent_model: Optional[str] = None
    dedup_verdict: Optional[str] = None
    sample_lines: list[str] = field(default_factory=list)
    # delivery
    report_sent_at: Optional[float] = None
    delivery_failed_at: Optional[float] = None
    delivery_failure_reason: Optional[str] = None


@dataclass
class FixResult:
    """What the coding-agent adapter returns."""
    status: str
    diff: str = ""
    files: dict[str, str] = field(default_factory=dict)
    smoke_passed: bool = False
    narrative: str = ""
    agent_log: str = ""
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    turns: Optional[int] = None
    wall_clock_s: Optional[float] = None


@dataclass
class PullRequest:
    """A bot PR as the code host reports it."""
    number: int
    url: str
    branch: str
    base: str
    diff: str = ""


@dataclass
class Report:
    """The one-per-incident payload (ESSENCE §10)."""
    incident_id: int
    slug: str
    severity: str
    confidence: str
    summary: str
    root_cause: str
    sample_lines: list[str]
    status: str
    diff: str
    smoke_passed: Optional[bool]
    narrative: str
    pr_url: Optional[str]
    pr_skip_reason: Optional[str]
    triage_model: str
    coding_agent_model: str
    dedup_verdict: Optional[str]
    agent_log: str = ""
