"""Coding agent — given an incident and a sandbox, drafts a fix and runs the
app's tests (the smoke gate). `CannedCodingAgent` recognizes a small set of
seeded bugs and applies the known fix. A real agent investigates and writes the
patch itself — implement `CLICodingAgent` (ESSENCE §4E, §6.2)."""
from dataclasses import dataclass, field

from services._fixes import CANNED_FIXES


@dataclass
class FixResult:
    status: str  # succeeded | smoke_failed | diff_empty | deferred
    diff: str = ""
    files: dict = field(default_factory=dict)
    smoke_passed: bool = False
    smoke_output: str = ""
    narrative: str = ""


class CannedCodingAgent:
    def attempt_fix(self, incident, sandbox) -> FixResult:
        fix = CANNED_FIXES.get(incident.slug)
        if fix is None:
            return FixResult(
                status="deferred",
                narrative=f"No canned fix for '{incident.slug}'. A real coding agent would write one.",
            )
        sandbox.write_files(fix)
        passed, out = sandbox.run_tests()
        diff = sandbox.diff()
        if not diff:
            return FixResult(status="diff_empty", smoke_output=out, narrative="no change produced")
        return FixResult(
            status="succeeded" if passed else "smoke_failed",
            diff=diff, files=fix, smoke_passed=passed, smoke_output=out,
            narrative="applied the fix and ran the app's tests in the sandbox",
        )


class CLICodingAgent:
    """REAL coding-agent adapter — IMPLEMENT ME (ESSENCE §4E, §6.2). Run your
    coding CLI against the sandbox with the incident inlined; return diff + smoke."""

    def attempt_fix(self, incident, sandbox) -> FixResult:
        raise NotImplementedError("Wire your coding agent — ESSENCE.md §6.2.")
