"""Resume & backfill logic, digests, retention (ESSENCE §12, §7)."""
from watchdog import jobs
from watchdog.config import Config, Rule
from watchdog.models import Incident, LogLine
from watchdog.notifier import CollectingNotifier
from watchdog.service import Service
from watchdog.store import Datastore


class _Pipeline:
    """A stub pipeline that records poll calls and can be made to fail."""

    def __init__(self, store):
        self.store = store
        self.notifier = CollectingNotifier()
        self.calls = []
        self.fail = False

    def poll(self, rule, query, since, until):
        if self.fail:
            raise RuntimeError("boom")
        self.calls.append((rule, since, until))

        class R:  # minimal result
            pass
        return R()

    def wait_for_fixes(self, timeout=None):
        pass


def _service(tmp_path, **over):
    store = Datastore(":memory:")
    cfg = Config(rules=[Rule("r", "{}")], db_path=":memory:",
                 reports_dir=str(tmp_path), max_backfill_s=7200, **over)
    return Service(cfg, _Pipeline(store), store), store


def test_cold_start_begins_at_now(tmp_path):
    svc, store = _service(tmp_path)
    since = svc.initial_since("r", now=1_000.0)
    assert since == 1_000.0  # no backfill configured
    assert store.load_resume("r") == 1_000.0


def test_cold_start_with_backfill(tmp_path):
    svc, store = _service(tmp_path, cold_backfill_s=600)
    since = svc.initial_since("r", now=1_000.0)
    assert since == 400.0


def test_warm_restart_bridges_from_saved(tmp_path):
    svc, store = _service(tmp_path)
    store.save_resume("r", 900.0)
    since = svc.initial_since("r", now=1_000.0)
    assert since == 900.0


def test_warm_restart_capped_at_max_backfill(tmp_path):
    svc, store = _service(tmp_path)  # max_backfill_s=7200
    store.save_resume("r", 0.0)  # a very old resume point
    since = svc.initial_since("r", now=100_000.0)
    assert since == 100_000.0 - 7200  # capped, won't replay days


def test_failed_poll_does_not_advance_resume(tmp_path):
    svc, store = _service(tmp_path)
    store.save_resume("r", 500.0)
    svc.pipeline.fail = True
    rule = svc.cfg.rules[0]
    svc.poll_once(rule, now=1_000.0)
    assert store.load_resume("r") == 500.0  # not advanced
    assert "r" not in svc.last_successful_poll


def test_successful_poll_advances_resume(tmp_path):
    svc, store = _service(tmp_path)
    store.save_resume("r", 500.0)
    rule = svc.cfg.rules[0]
    svc.poll_once(rule, now=1_000.0)
    assert store.load_resume("r") == 1_000.0
    assert svc.last_successful_poll["r"] == 1_000.0


# --- periodic jobs ---

def test_retention_sweeps_old_lines_not_incidents(tmp_path):
    store = Datastore(":memory:", time_bucket_s=86_400)
    from watchdog.fingerprint import line_fingerprint
    old = LogLine(ts=100.0, text="old error")
    new = LogLine(ts=1_000_000.0, text="new error")
    store.ingest("r", [(line_fingerprint(old.text), old)])
    store.ingest("r", [(line_fingerprint(new.text), new)])
    store.create_incident(Incident(incident_fingerprint="x", slug="s", severity="high",
                                   confidence="high", first_seen=100.0, last_seen=100.0,
                                   created_at=100.0))
    deleted = jobs.retention_sweep(store, now=1_000_000.0, retention_s=3600)
    assert deleted == 1  # the old line
    assert store.counts()["incidents"] == 1  # incidents never swept
    store.close()


def test_benign_digest_skips_when_empty(tmp_path):
    store = Datastore(":memory:")
    notifier = CollectingNotifier()
    assert jobs.benign_digest(store, notifier, now=1_000.0) is False
    assert notifier.sent == []  # no "nothing to report" noise
    store.close()


def test_benign_digest_sends_when_present(tmp_path):
    store = Datastore(":memory:")
    notifier = CollectingNotifier()
    store.record_noop("fp" * 4, "benign ping", 1_000.0)
    assert jobs.benign_digest(store, notifier, now=1_000.0) is True
    assert len(notifier.sent) == 1
    store.close()
