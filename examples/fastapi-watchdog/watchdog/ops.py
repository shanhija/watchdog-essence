"""On-demand operator actions (ESSENCE §7): mute, manual re-run, manual backfill.

Run as: python -m watchdog.ops <command> [args]. These reach the same datastore the
resident service uses.
"""
from __future__ import annotations

import sys
import time

from .config import Config
from .service import build_pipeline

_BACKFILL_LOCK = "watchdog_data/.backfill.lock"


def mute(incident_fingerprint: str, reason: str = "muted by operator") -> None:
    """Mark an incident fingerprint as benign on demand — future occurrences skip fix + alert."""
    cfg = Config.from_env()
    _, store = build_pipeline(cfg)
    store.record_noop(incident_fingerprint, reason, time.time())
    print(f"muted {incident_fingerprint}")
    store.close()


def rerun(incident_id: int) -> None:
    """Re-attempt the fix for an existing incident using its stored analysis (no re-clustering).

    Deliberately bypasses the severity/confidence gate — it is an explicit human override.
    """
    cfg = Config.from_env()
    pipeline, store = build_pipeline(cfg)
    inc = store.get_incident(incident_id)
    if inc is None:
        print(f"no incident {incident_id}")
        return
    pipeline.run_fix(incident_id)  # synchronous so the operator sees it finish
    print(f"re-ran fix for incident {incident_id}")
    store.close()


def backfill(hours: float) -> None:
    """Replay the last N hours for every rule on demand. Single-flighted; idempotent."""
    import os

    os.makedirs("watchdog_data", exist_ok=True)
    if os.path.exists(_BACKFILL_LOCK):
        print("a backfill is already in progress; aborting")
        return
    open(_BACKFILL_LOCK, "w").close()
    try:
        cfg = Config.from_env()
        pipeline, store = build_pipeline(cfg)
        now = time.time()
        since = now - hours * 3600
        for rule in cfg.rules:
            result = pipeline.poll(rule.name, rule.query, since, now)
            print(f"backfill {rule.name}: {result}")
        pipeline.wait_for_fixes(timeout=cfg.agent_wall_clock_s)
        store.close()
    finally:
        os.remove(_BACKFILL_LOCK)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, *rest = argv
    if cmd == "mute" and rest:
        mute(rest[0], rest[1] if len(rest) > 1 else "muted by operator")
    elif cmd == "rerun" and rest:
        rerun(int(rest[0]))
    elif cmd == "backfill" and rest:
        backfill(float(rest[0]))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
