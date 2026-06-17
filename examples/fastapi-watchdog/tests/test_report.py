"""Report rendering — golden-ish assertions per status (ESSENCE §10, §14)."""
from watchdog.models import Incident
from watchdog.notifier import (
    render_attachment,
    render_body,
    render_subject,
    report_from_incident,
)


def _incident(**kw):
    base = dict(
        id=42, slug="upstream-429-retries", severity="high", confidence="high",
        root_cause="upstream returns 429 without honoring Retry-After",
        summary="Retry cascade against the rate-limited upstream",
        sample_lines=["Attempt 1/3 ... 429", "All attempts failed"],
        status="succeeded", diff="diff --git a/x b/x\n+fixed\n", smoke_result=True,
        narrative="Honored Retry-After with jittered backoff.",
        pr_url="https://example.test/pr/101", triage_model="claude-opus-4-8",
        coding_agent_model="claude-opus-4-8",
    )
    base.update(kw)
    return Incident(**base)


def test_subject_carries_severity_slug_status():
    r = report_from_incident(_incident())
    assert render_subject(r) == "[watchdog] HIGH upstream-429-retries — succeeded"


def test_body_includes_signal_and_diff():
    body = render_body(report_from_incident(_incident()))
    assert "## Summary" in body
    assert "## Root-cause hypothesis" in body
    assert "Attempt 1/3 ... 429" in body  # raw sample lines, the actual signal
    assert "```diff" in body
    assert "https://example.test/pr/101" in body
    assert "Smoke gate:** passed" in body


def test_deferred_report_states_no_pr_and_why():
    body = render_body(report_from_incident(
        _incident(status="deferred", diff="", pr_url=None,
                  pr_skip_reason="fix deferred (too big to do safely)",
                  smoke_result=None, narrative="This needs a new module; here's the plan...")
    ))
    assert "none (fix deferred (too big to do safely))" in body
    assert "(no diff)" in body
    assert "Smoke gate:** n/a" in body
    assert "here's the plan" in body  # the narrative is the valuable part on a deferral


def test_agent_log_tail_in_body_full_in_attachment():
    inc = _incident(agent_log="L" * 5000)
    r = report_from_incident(inc)
    body = render_body(r)
    assert "Agent log (tail" in body
    assert len(render_attachment(r)) == 5000  # full log in the attachment
    assert body.count("L") < 5000  # only a tail in the body
