"""The app's own tests — the smoke gate the watchdog's fix must pass.

These cover the happy paths and pass against the buggy code (they only ask for keys
that exist). The fix the watchdog drafts should ADD a regression test for the missing
-key case (currently a 500) asserting a clean 404 — see app/main.py:get_item.

Smoke command (shared by the agent and the gate):  python -m pytest app/tests -q
"""
from fastapi.testclient import TestClient

from app.main import STORE, app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_get_existing_key():
    STORE["hello"] = "world"
    r = client.get("/items/hello")
    assert r.status_code == 200
    assert r.json() == {"key": "hello", "value": "world"}


def test_post_then_get():
    r = client.post("/items/order-42", json={"value": "shipped"})
    assert r.status_code == 200
    r = client.get("/items/order-42")
    assert r.status_code == 200
    assert r.json()["value"] == "shipped"
