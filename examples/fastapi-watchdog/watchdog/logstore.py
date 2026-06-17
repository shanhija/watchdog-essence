"""Log store port + the Loki adapter (ESSENCE §3, Appendix B).

The pipeline depends only on ``LogStore.fetch(rule, since, until) -> LogLine[]``. The
log store is an *infrastructure* role: many non-AI implementations, so it stays abstract.
This environment ships logs to Loki, so the concrete adapter queries Loki's query_range API.
"""
from __future__ import annotations

from typing import Protocol

import httpx

from .models import LogLine


class LogStore(Protocol):
    def fetch(self, query: str, since: float, until: float) -> list[LogLine]:
        """Return error-level lines in the window [since, until] (epoch seconds)."""
        ...


class LokiLogStore:
    """Queries Loki's /loki/api/v1/query_range endpoint."""

    def __init__(self, base_url: str, *, timeout: float = 10.0, max_lines: int = 5000) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_lines = max_lines

    def fetch(self, query: str, since: float, until: float) -> list[LogLine]:
        params = {
            "query": query,
            "start": str(int(since * 1e9)),  # Loki wants nanoseconds
            "end": str(int(until * 1e9)),
            "limit": str(self.max_lines),
            "direction": "forward",
        }
        resp = httpx.get(
            f"{self.base_url}/loki/api/v1/query_range", params=params, timeout=self.timeout
        )
        resp.raise_for_status()
        data = resp.json()
        return _parse_loki(data)


def _parse_loki(data: dict) -> list[LogLine]:
    out: list[LogLine] = []
    for stream in data.get("data", {}).get("result", []):
        labels = stream.get("stream", {})
        for value in stream.get("values", []):
            # value is [ "<ns timestamp>", "<line>" ]
            ts_ns, text = value[0], value[1]
            out.append(LogLine(ts=int(ts_ns) / 1e9, text=text, labels=dict(labels)))
    out.sort(key=lambda l: l.ts)
    return out


class InMemoryLogStore:
    """A fake log store for tests and local dev — fetch returns lines you pushed."""

    def __init__(self) -> None:
        self.lines: list[LogLine] = []

    def push(self, line: LogLine) -> None:
        self.lines.append(line)

    def fetch(self, query: str, since: float, until: float) -> list[LogLine]:
        return [l for l in self.lines if since <= l.ts <= until]
