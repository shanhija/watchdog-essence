"""Per-incident-fingerprint locks (ESSENCE §13).

An in-process lock around create/link so two concurrent polls can't both create the
"same" new incident. If you scale out to multiple instances, swap this for a
shared/distributed lock with the same interface.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager


class FingerprintLocks:
    def __init__(self) -> None:
        self._global = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    @contextmanager
    def lock(self, fingerprint: str):
        with self._global:
            lk = self._locks.setdefault(fingerprint, threading.Lock())
        lk.acquire()
        try:
            yield
        finally:
            lk.release()
