"""Smoke-path integration: a real sandbox + the exact smoke command, token-free (ESSENCE §14).

Proves "green for the agent == the gate passes": we materialize a real isolated copy of
the app, let a *scripted* (no-LLM) agent apply a fix, run the actual smoke command, and
assert the wiring produces a SUCCEEDED status, a report, and no PR (auto-PR off).
"""
import shutil
from pathlib import Path

import pytest

from watchdog.budget import LLMBudget
from watchdog.codehost import FakeCodeHost
from watchdog.config import Config, Rule
from watchdog.logstore import InMemoryLogStore
from watchdog.notifier import CollectingNotifier
from watchdog.agent import FakeCodingAgent
from watchdog.models import Incident
from watchdog.pipeline import Pipeline
from watchdog.store import Datastore
from watchdog.triage import FakeTriageModel

REPO_ROOT = Path(__file__).resolve().parents[1]

# A real fix for the kvstore KeyError bug: return a clean 404 instead of 500-ing.
FIXED_MAIN = '''\
"""A tiny FastAPI key/value service (watchdog-fixed: missing key -> 404)."""
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.loki_logging import configure_logging

log = logging.getLogger("kvstore")
configure_logging(log)

app = FastAPI(title="kvstore")

STORE: dict[str, str] = {"hello": "world", "ping": "pong"}


class Item(BaseModel):
    value: str


@app.middleware("http")
async def catch_and_log(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001
        log.error("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.get("/healthz")
def healthz():
    return {"ok": True, "keys": len(STORE)}


@app.post("/items/{key}")
def put_item(key: str, item: Item):
    STORE[key] = item.value
    log.info("stored key=%s", key)
    return {"key": key, "value": item.value}


@app.get("/items/{key}")
def get_item(key: str):
    if key not in STORE:
        raise HTTPException(status_code=404, detail=f"no such key: {key}")
    return {"key": key, "value": STORE[key]}
'''


@pytest.mark.skipif(shutil.which("git") is None, reason="git required for the sandbox")
def test_real_sandbox_fix_succeeds_and_reports(tmp_path):
    cfg = Config(
        rules=[Rule("kvstore-errors", "{}")],
        db_path=":memory:",
        repo_root=str(REPO_ROOT),
        reports_dir=str(tmp_path / "reports"),
        smoke_command="python -m pytest app/tests -q",
        auto_pr_enabled=False,
        prod_branch="main",
        review_branch="integration",
    )
    store = Datastore(":memory:")
    notifier = CollectingNotifier()
    agent = FakeCodingAgent(
        edits={"app/main.py": FIXED_MAIN},
        repo="kvstore", smoke_command=cfg.smoke_command,
        max_lines=cfg.fix_size_max_lines, max_files=cfg.fix_size_max_files,
    )
    p = Pipeline(
        cfg, store=store, log_store=InMemoryLogStore(), triage=FakeTriageModel([]),
        coding_agent=agent, code_host=FakeCodeHost(), notifier=notifier,
        budget=LLMBudget(100, 100), run_fixes_async=False,
    )
    incident_id = store.create_incident(Incident(
        incident_fingerprint="deadbeef" * 8, slug="key-error", severity="high",
        confidence="high", root_cause="missing dict key raises KeyError",
        summary="GET /items/{key} 500s on a missing key", affected_files=["app/main.py"],
        first_seen=1.0, last_seen=1.0, created_at=1.0,
        sample_lines=["unhandled error on GET /items/order-99 ... KeyError: 'order-99'"],
    ))

    p.run_fix(incident_id)

    inc = store.get_incident(incident_id)
    assert inc.status == "succeeded", inc.agent_log
    assert inc.smoke_result is True
    assert inc.diff and "HTTPException" in inc.diff  # the real fix is in the diff
    assert inc.pr_url is None  # auto-PR off
    assert "auto-PR disabled" in (inc.pr_skip_reason or "")
    assert len(notifier.sent) == 1  # exactly one report
    assert inc.report_sent_at is not None
    store.close()
