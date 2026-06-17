"""The app's own tests.

These cover the happy paths and pass against the current code (they only ask for keys
that exist). The missing-key case currently 500s — see app/main.py:get_item.

Run them:  python -m pytest app/tests -q
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
