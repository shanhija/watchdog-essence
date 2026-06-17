"""Pipeline poll path with all collaborators faked (ESSENCE §14 functional tests)."""
from watchdog.budget import LLMBudget
from watchdog.models import LogLine

from .conftest import make_pipeline

RULE = "kvstore-errors"
QUERY = '{service="kvstore",level="ERROR"}'

# In a fresh in-memory DB the first candidate gets id=1.
LOW = [{"line_ids": [1], "existing_incident_id": None, "slug": "key-error",
        "severity": "low", "confidence": "low", "summary": "s", "root_cause": "r"}]
NONE = []


def _push(pipeline, texts, clock):
    for t in texts:
        pipeline.log_store.push(LogLine(ts=clock(), text=t))


def test_poll_skips_everything_when_no_lines(cfg, store, clock):
    p = make_pipeline(cfg, store, clock, triage_groupings=LOW)
    result = p.poll(RULE, QUERY, clock() - 60, clock())
    assert result.skipped_no_candidates
    assert result.clustering_calls == 0
    assert p.triage.calls == 0  # no LLM call on an empty window


def test_poll_skips_llm_when_budget_exhausted(cfg, store, clock):
    p = make_pipeline(cfg, store, clock, triage_groupings=LOW)
    p.budget = LLMBudget(0, 0, now_fn=clock)  # exhausted
    _push(p, ["some error"], clock)
    result = p.poll(RULE, QUERY, clock() - 60, clock())
    assert result.skipped_budget
    assert result.clustering_calls == 0
    assert store.candidates(RULE)  # candidates remain for next poll


def test_poll_creates_incident_and_is_idempotent(cfg, store, clock):
    p = make_pipeline(cfg, store, clock, triage_groupings=LOW)
    _push(p, ["KeyError 'order-99'"], clock)
    r1 = p.poll(RULE, QUERY, clock() - 60, clock())
    assert r1.incidents_created == 1
    assert store.counts()["incidents"] == 1
    # Replay the same window: upsert bumps nothing new → no second incident.
    r2 = p.poll(RULE, QUERY, clock() - 60, clock())
    assert r2.incidents_created == 0
    assert store.counts()["incidents"] == 1


def test_poll_marks_orphan_lines_considered(cfg, store, clock):
    p = make_pipeline(cfg, store, clock, triage_groupings=NONE)  # model claims nothing
    _push(p, ["unclustered error"], clock)
    p.poll(RULE, QUERY, clock() - 60, clock())
    assert store.candidates(RULE) == []  # orphan stamped considered


def test_hallucinations_counted(cfg, store, clock):
    p = make_pipeline(
        cfg, store, clock,
        triage_groupings=[{"line_ids": [99999], "existing_incident_id": None,
                           "slug": "x", "severity": "high", "confidence": "high"}],
    )
    _push(p, ["real error"], clock)
    result = p.poll(RULE, QUERY, clock() - 60, clock())
    assert result.hallucinations["unknown_line_id"] == 1
    assert result.incidents_created == 0
