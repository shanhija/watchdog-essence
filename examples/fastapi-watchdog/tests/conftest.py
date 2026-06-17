"""Shared fixtures: an in-memory pipeline wired entirely with fakes (ESSENCE §14)."""
import pytest

from watchdog.agent import AgentRun, FakeCodingAgent
from watchdog.budget import LLMBudget
from watchdog.codehost import FakeCodeHost
from watchdog.config import Config, Rule
from watchdog.fingerprint import line_fingerprint
from watchdog.logstore import InMemoryLogStore
from watchdog.models import LogLine
from watchdog.notifier import CollectingNotifier
from watchdog.pipeline import Pipeline
from watchdog.store import Datastore
from watchdog.triage import FakeTriageModel


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store():
    s = Datastore(":memory:", time_bucket_s=86_400)
    yield s
    s.close()


@pytest.fixture
def cfg(tmp_path):
    return Config(
        rules=[Rule("kvstore-errors", '{service="kvstore",level="ERROR"}')],
        db_path=":memory:",
        repo_root=str(tmp_path),
        reports_dir=str(tmp_path / "reports"),
        smoke_command="true",
        auto_pr_enabled=False,
        active_window_s=3600,
    )


def make_pipeline(cfg, store, clock, *, triage_groupings=None, agent=None, code_host=None,
                  notifier=None, adjudicator=None):
    triage = FakeTriageModel(triage_groupings or [])
    agent = agent or FakeCodingAgent()
    code_host = code_host or FakeCodeHost()
    notifier = notifier or CollectingNotifier()
    budget = LLMBudget(1000, 10000, now_fn=clock)
    return Pipeline(
        cfg, store=store, log_store=InMemoryLogStore(), triage=triage, coding_agent=agent,
        code_host=code_host, notifier=notifier, budget=budget, adjudicator=adjudicator,
        now_fn=clock, run_fixes_async=False,
    )


@pytest.fixture
def pipeline_factory(cfg, store, clock):
    def _make(**kw):
        return make_pipeline(cfg, store, clock, **kw)
    return _make


def ingest_lines(store, rule, texts, clock):
    batch = [(line_fingerprint(t), LogLine(ts=clock(), text=t)) for t in texts]
    store.ingest(rule, batch)
    return store.candidates(rule)
