"""A tiny FastAPI key/value service.

    GET  /items/{key}   -> the stored value      (BUG: assumes the key exists)
    POST /items/{key}   -> store / extend a value
    GET  /healthz       -> liveness

Run locally:   uvicorn app.main:app --reload
In compose:    the `app` service runs this and ships error logs to Loki.

The bug: a missing dict key raises ``KeyError`` -> a 500 + an error log (left in on
purpose). The obvious fix is to check the key and return a clean 404.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.loki_logging import configure_logging

log = logging.getLogger("kvstore")
configure_logging(log)

app = FastAPI(title="kvstore")

# The "database": an in-memory dict, seeded with a couple of keys and extendable at
# runtime via POST. A real service would use a real datastore; the bug is identical.
STORE: dict[str, str] = {"hello": "world", "ping": "pong"}


class Item(BaseModel):
    value: str


@app.middleware("http")
async def catch_and_log(request: Request, call_next):
    """Turn any unhandled exception into a 500 and log it loudly with a traceback,
    so failures show up as clear, traceback-bearing ERROR lines in the logs.
    """
    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001 - first-line defense; logs and 500s
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
    # BUG: assumes the key is present. A missing key raises KeyError, which the
    # middleware turns into a 500 and logs as an ERROR. (Should arguably be a 404.)
    return {"key": key, "value": STORE[key]}
