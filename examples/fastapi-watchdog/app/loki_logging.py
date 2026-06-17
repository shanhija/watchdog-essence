"""Logging setup for the kvstore app: pretty stdout plus — when ``LOKI_URL`` is
set — pushing WARNING/ERROR records (with tracebacks) to Loki's HTTP push API, so
errors are queryable in Loki.

In production a log shipper (Promtail, the Loki Docker driver, Fluent Bit, Vector,
a cloud logging agent…) would do this out-of-band. Here the app pushes directly so
the whole thing is one `docker compose up` with no shipper to configure — swapping
in a real shipper changes nothing about what ends up in Loki.
"""
import logging
import os
import time

try:  # httpx ships with the app (FastAPI's TestClient uses it too)
    import httpx
except Exception:  # pragma: no cover - app still runs, just without Loki push
    httpx = None


class LokiHandler(logging.Handler):
    """Push each record to Loki as one log line, labelled by service + level."""

    def __init__(self, url: str, service: str) -> None:
        super().__init__()
        self.push_url = url.rstrip("/") + "/loki/api/v1/push"
        self.service = service

    def emit(self, record: logging.LogRecord) -> None:
        if httpx is None:
            return
        try:
            # format() includes the traceback when record.exc_info is set, so the
            # pushed line carries "KeyError: '<key>'" and the app/main.py frame.
            line = self.format(record)
            ts = str(time.time_ns())
            payload = {
                "streams": [
                    {
                        "stream": {"service": self.service, "level": record.levelname},
                        "values": [[ts, line]],
                    }
                ]
            }
            httpx.post(self.push_url, json=payload, timeout=2.0)
        except Exception:
            # Logging must never take down the app it is observing.
            pass


def configure_logging(logger: logging.Logger) -> None:
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    url = os.environ.get("LOKI_URL")
    if url:
        loki = LokiHandler(url, os.environ.get("APP_SERVICE", "kvstore"))
        loki.setLevel(logging.WARNING)  # only warnings + errors ship to Loki
        loki.setFormatter(fmt)
        logger.addHandler(loki)

    logger.propagate = False
