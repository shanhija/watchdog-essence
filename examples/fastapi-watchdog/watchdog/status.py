"""Fix-attempt status taxonomy, the gate, and severity/confidence (ESSENCE §11, §9, App E).

These are pure functions over scalars — the highest-value regression-test target after
fingerprinting, so they live alone with no I/O.
"""
from __future__ import annotations

# --- fix-attempt outcomes (ESSENCE §11) ---
SUCCEEDED = "succeeded"
DEFERRED = "deferred"
SMOKE_FAILED = "smoke_failed"
DIFF_EMPTY = "diff_empty"
TIMED_OUT = "timed_out"
TURNS_EXHAUSTED = "turns_exhausted"
CRASHED = "crashed"
SKIPPED = "skipped"

# --- severity / confidence vocab (ESSENCE §3) ---
SEVERITIES = ("noop", "low", "medium", "high")
CONFIDENCES = ("low", "medium", "high")
_ACTIONABLE_CONFIDENCE = {"medium", "high"}


def classify_status(
    *,
    exit_code: int,
    hit_turn_budget: bool,
    hit_wall_clock: bool,
    diff_empty: bool,
    smoke_passed: bool,
    has_narrative: bool,
) -> str:
    """Map a finished agent run to a status. Order matters (Appendix E)."""
    if hit_turn_budget:
        return TURNS_EXHAUSTED
    if hit_wall_clock:
        return TIMED_OUT
    if exit_code != 0:
        return CRASHED
    if diff_empty:
        return DEFERRED if has_narrative else DIFF_EMPTY
    if not smoke_passed:
        return SMOKE_FAILED
    return SUCCEEDED


def is_actionable(severity: str, confidence: str) -> bool:
    """Attempt a fix only for incidents that are not benign and confident enough.

    actionable ⇔ severity != "noop" AND confidence ∈ {medium, high}
    """
    return severity != "noop" and confidence in _ACTIONABLE_CONFIDENCE


def should_open_pr(
    *,
    severity: str,
    confidence: str,
    status: str,
    auto_pr_enabled: bool,
    strict: bool = False,
) -> bool:
    """open_a_PR ⇔ actionable AND status == SUCCEEDED AND auto_pr_enabled.

    With ``strict`` also require severity ∈ {medium, high} AND confidence == high.
    """
    if not (is_actionable(severity, confidence) and status == SUCCEEDED and auto_pr_enabled):
        return False
    if strict:
        return severity in ("medium", "high") and confidence == "high"
    return True
