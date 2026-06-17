"""LLM call budgets — hourly + daily rate limiter (ESSENCE §8, Appendix H).

An LLM pointed at a firehose of logs will bankrupt you by default. Check before the
clustering call; if the budget is gone, skip and let the lines be retried next poll.
All LLM use (triage, fix, dedup adjudication) draws from the same accounting.
"""
from __future__ import annotations

import threading
import time
from collections import deque


class LLMBudget:
    def __init__(self, hourly: int, daily: int, *, now_fn=time.time) -> None:
        self.hourly = hourly
        self.daily = daily
        self._now = now_fn
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        cutoff = now - 86_400
        while self._calls and self._calls[0] < cutoff:
            self._calls.popleft()

    def _count_since(self, now: float, window: float) -> int:
        cutoff = now - window
        return sum(1 for t in self._calls if t >= cutoff)

    def available(self) -> bool:
        """True if a call is allowed under both the hourly and daily ceilings."""
        now = self._now()
        with self._lock:
            self._prune(now)
            return (
                self._count_since(now, 3_600) < self.hourly
                and self._count_since(now, 86_400) < self.daily
            )

    def charge(self) -> None:
        """Record that one LLM call happened (account every call against the budget)."""
        now = self._now()
        with self._lock:
            self._prune(now)
            self._calls.append(now)

    def try_charge(self) -> bool:
        """Atomically check-and-charge; returns False (and charges nothing) if exhausted."""
        now = self._now()
        with self._lock:
            self._prune(now)
            if (
                self._count_since(now, 3_600) >= self.hourly
                or self._count_since(now, 86_400) >= self.daily
            ):
                return False
            self._calls.append(now)
            return True
