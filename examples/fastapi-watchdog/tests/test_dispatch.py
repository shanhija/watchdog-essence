"""Dispatch logic — link vs create vs benign, safety net, re-emergence (ESSENCE §4D, §13)."""
from watchdog.models import Grouping

from .conftest import ingest_lines

RULE = "kvstore-errors"


def _grouping(line_ids, **kw):
    base = dict(line_ids=line_ids, existing_incident_id=None, slug="key-error",
                severity="medium", confidence="high", root_cause="missing key",
                summary="KeyError on missing key", affected_files=["app/main.py"])
    base.update(kw)
    return Grouping(**base)


def test_new_incident_created_and_actionable_returns_fix(pipeline_factory, store, clock):
    p = pipeline_factory()
    cands = ingest_lines(store, RULE, ["KeyError 'order-99'"], clock)
    cand_by_id = {c.id: c for c in cands}
    outcome = p._dispatch_one(_grouping([cands[0].id]), cand_by_id)
    assert outcome[0] == "fix"
    inc = store.get_incident(outcome[1])
    assert inc.severity == "medium" and inc.slug == "key-error"
    assert inc.sample_lines == ["KeyError 'order-99'"]


def test_low_confidence_incident_is_skipped_not_fixed(pipeline_factory, store, clock):
    p = pipeline_factory()
    cands = ingest_lines(store, RULE, ["weird thing"], clock)
    outcome = p._dispatch_one(_grouping([cands[0].id], confidence="low"), {c.id: c for c in cands})
    assert outcome == "created"


def test_benign_short_circuit_records_noop(pipeline_factory, store, clock):
    p = pipeline_factory()
    cands = ingest_lines(store, RULE, ["healthcheck ping"], clock)
    outcome = p._dispatch_one(
        _grouping([cands[0].id], severity="noop", is_known_noop=True, noop_reason="just a ping"),
        {c.id: c for c in cands},
    )
    assert outcome == "noop"
    from watchdog.fingerprint import incident_fingerprint
    ifp = incident_fingerprint([cands[0].line_fingerprint])
    assert store.is_known_noop(ifp)


def test_known_noop_suppresses_future(pipeline_factory, store, clock):
    p = pipeline_factory()
    cands = ingest_lines(store, RULE, ["benign noise"], clock)
    from watchdog.fingerprint import incident_fingerprint
    ifp = incident_fingerprint([cands[0].line_fingerprint])
    store.record_noop(ifp, "known", clock())
    outcome = p._dispatch_one(_grouping([cands[0].id]), {c.id: c for c in cands})
    assert outcome == "noop"


def test_link_bumps_existing_active_incident(pipeline_factory, store, clock):
    p = pipeline_factory()
    cands = ingest_lines(store, RULE, ["KeyError 'a'"], clock)
    created = p._dispatch_one(_grouping([cands[0].id]), {c.id: c for c in cands})
    incident_id = created[1]
    # A later poll's line links to it.
    cands2 = ingest_lines(store, RULE, ["KeyError 'b'"], clock)
    link = Grouping(line_ids=[cands2[-1].id], existing_incident_id=incident_id)
    outcome = p._dispatch_one(link, {c.id: c for c in cands2})
    assert outcome == "linked"  # recurrence → no fix, no alert
    assert store.get_incident(incident_id).occurrences == 2


def test_safety_net_merges_race_into_one_incident(pipeline_factory, store, clock):
    """Two 'new' groupings with the same fingerprint must not both create incidents."""
    p = pipeline_factory()
    cands = ingest_lines(store, RULE, ["KeyError 'x'"], clock)
    first = p._dispatch_one(_grouping([cands[0].id]), {c.id: c for c in cands})
    assert first[0] == "fix"
    # The same fingerprint resurfaces on a later poll as a brand-new grouping (the model
    # failed to link). Advance the clock so the upsert bumps last_seen → candidate again.
    clock.t += 1
    cands2 = ingest_lines(store, RULE, ["KeyError 'x'"], clock)
    same = next(c for c in cands2 if c.line_fingerprint == cands[0].line_fingerprint)
    second = p._dispatch_one(_grouping([same.id]), {same.id: same})
    assert second == "linked"  # safety net caught it
    assert store.counts()["incidents"] == 1


def test_link_target_aged_out_becomes_fresh_ticket(pipeline_factory, store, cfg, clock):
    """Re-emergence is a new ticket (principle #10)."""
    p = pipeline_factory()
    cands = ingest_lines(store, RULE, ["KeyError 'x'"], clock)
    created = p._dispatch_one(_grouping([cands[0].id]), {c.id: c for c in cands})
    incident_id = created[1]
    # Advance the clock past the active window so the target ages out.
    clock.t += cfg.active_window_s + 10
    cands2 = ingest_lines(store, RULE, ["KeyError 'y'"], clock)
    link = Grouping(line_ids=[cands2[-1].id], existing_incident_id=incident_id)
    outcome = p._dispatch_one(link, {c.id: c for c in cands2})
    assert outcome != "linked"  # did NOT silently revive the aged-out incident
    assert store.counts()["incidents"] == 2  # a fresh ticket was created
