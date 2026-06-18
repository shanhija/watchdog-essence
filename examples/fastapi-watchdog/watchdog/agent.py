"""The coding agent — the fix draft (ESSENCE §6.2, Appendix D, Appendix E).

The agent runs non-interactively in the sandbox against the pristine copy, with the
incident **inlined into the prompt** (never a side file — agents sandbox file tools to the
working directory). Bounded by a turn budget and a wall-clock cap. This role is inherently
LLM-backed.

The base class owns the orchestration that's identical for every agent backend: run the
agent → commit → diff → run the smoke gate → classify the status. A concrete backend only
has to implement ``_invoke_agent`` (run the headless agent and report how it exited).
"""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional, Protocol

from . import status as st
from .fingerprint import changed_files
from .models import FixResult, Incident
from .sandbox import Sandbox

PROMPT_TEMPLATE = """\
You are debugging a production error in {repo}. You are in a FRESH, isolated checkout — nothing from
any previous run is present; your current directory is the repo root.

INCIDENT (the raw signal that triggered this):
  Severity: {severity}
  Analyzer's root-cause hypothesis — a STARTING POINT, not a verdict. Re-read the samples and judge
  for yourself:
    {root_cause}
  Summary: {summary}
  Sample log lines:
{samples}

HARD SCOPE. Edit ONLY these files (plus their nearest shared subsystem subtree):
    {affected_files}
  If your investigation shows the real bug is elsewhere, do NOT silently widen. Leave a one-line
  comment in the FIRST in-scope file (e.g. "# real fix needed in <path>") and exit, so the next run
  — with better analysis — fixes it in the right place. A wandering diff is a failure mode, not a fix.

DEFAULT TO PRODUCING A FIX within scope. Common categories:
  - rate limits / 429 → honour Retry-After + longer/jittered backoff; distinguish transient vs persistent.
  - timeouts → tune the timeout, add a circuit breaker, surface a typed exception.
  - 5xx from upstreams → classify retryable vs not; log diagnostic context.
  - parse / KeyError on external data → defensive validation + a clear, typed, logged error.
  - silent failures → make them loud (log at error with context).

ONLY FIX THE REPORTED INCIDENT. You will notice other smells — do NOT fix them. One incident → one
focused PR. Note anything else as a "noted (not fixed)" comment for a human to triage.

KEEP IT MINOR, OR DEFER. Budget: <= ~{max_lines} added/changed lines across <= {max_files} files. If
the real fix is bigger (a new module, a cross-cutting refactor, a schema migration), DO NOT IMPLEMENT
IT, DO NOT COMMIT. Make your FINAL message a clear plan: problem, approach, risks, files + rough size,
why you deferred. Leave the checkout pristine (no "defer" comment in source). A clean deferral with a
good explanation is a GOOD outcome.

RUN THE TESTS. Run exactly this command from the repo root — it is what the gate runs, so if it's
green for you, the gate passes:
    {smoke_command}

Your fix must: stay in scope · be the SMALLEST CORRECT change · add a regression test when feasible ·
surface failures via typed errors / logging (never silently swallow) · introduce no backwards-compat
shims · pass the smoke command · end with ONE commit:
    git add -A && git commit -m "<scope>: <one-line summary>"
(or a clean no-commit deferral).
"""


def build_prompt(inc: Incident, *, repo: str, smoke_command: str,
                 max_lines: int, max_files: int) -> str:
    samples = "\n".join(f"    {i}. {s}" for i, s in enumerate(inc.sample_lines, 1)) or "    (none)"
    affected = ", ".join(inc.affected_files) or "(no specific files identified — investigate)"
    return PROMPT_TEMPLATE.format(
        repo=repo,
        severity=inc.severity,
        root_cause=inc.root_cause,
        summary=inc.summary,
        samples=samples,
        affected_files=affected,
        max_lines=max_lines,
        max_files=max_files,
        smoke_command=smoke_command,
    )


@dataclass
class AgentRun:
    """The raw result of invoking the headless agent (before commit/diff/smoke)."""
    exit_code: int
    narrative: str = ""
    hit_turn_budget: bool = False
    hit_wall_clock: bool = False
    log: str = ""
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    turns: Optional[int] = None
    wall_clock_s: Optional[float] = None


class CodingAgent(Protocol):
    def attempt_fix(self, incident: Incident, sandbox: Sandbox) -> FixResult: ...


class BaseCodingAgent:
    """Shared orchestration: run agent → commit → diff → smoke gate → classify."""

    def __init__(
        self,
        *,
        repo: str,
        smoke_command: str,
        turn_budget: int,
        wall_clock_s: int,
        max_lines: int,
        max_files: int,
        model: str = "",
    ) -> None:
        self.repo = repo
        self.smoke_command = smoke_command
        self.turn_budget = turn_budget
        self.wall_clock_s = wall_clock_s
        self.max_lines = max_lines
        self.max_files = max_files
        self.model = model

    def _invoke_agent(self, prompt: str, sandbox: Sandbox) -> AgentRun:  # pragma: no cover
        raise NotImplementedError

    def attempt_fix(self, incident: Incident, sandbox: Sandbox) -> FixResult:
        prompt = build_prompt(
            incident,
            repo=self.repo,
            smoke_command=self.smoke_command,
            max_lines=self.max_lines,
            max_files=self.max_files,
        )
        run = self._invoke_agent(prompt, sandbox)

        # After the agent exits, commit any changes and compute the diff (§4E.4).
        if hasattr(sandbox, "commit"):
            sandbox.commit("watchdog: agent fix attempt")
        diff = sandbox.diff()
        diff_empty = not diff.strip()

        # Smoke gate (§4F): only run if there's actually a diff to test.
        smoke_passed = False
        if not diff_empty:
            smoke_passed, smoke_log = sandbox.run_tests()
            run.log = (run.log + "\n--- smoke gate ---\n" + smoke_log).strip()

        status = st.classify_status(
            exit_code=run.exit_code,
            hit_turn_budget=run.hit_turn_budget,
            hit_wall_clock=run.hit_wall_clock,
            diff_empty=diff_empty,
            smoke_passed=smoke_passed,
            has_narrative=bool(run.narrative.strip()),
        )
        files = {p: "" for p in changed_files(diff)}  # path list; content not needed downstream
        return FixResult(
            status=status,
            diff=diff,
            files=files,
            smoke_passed=smoke_passed,
            narrative=run.narrative,
            agent_log=run.log,
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
            turns=run.turns,
            wall_clock_s=run.wall_clock_s,
        )


class ClaudeCliCodingAgent(BaseCodingAgent):
    """Runs the Claude Code CLI headless inside the sandbox.

    The CLI/SDK is a dependency the *service image* ships with; it is credentialed via the
    environment (ANTHROPIC_API_KEY), never on a logged argv. Bound by ``--max-turns`` and a
    subprocess wall-clock ``timeout``. Backend specifics (exact flags) are isolated here so
    a different autonomous agent can be swapped behind the same interface.
    """

    def __init__(self, *, cli_cmd: str = "claude", api_key: str = "", **kw) -> None:
        super().__init__(**kw)
        self.cli_cmd = cli_cmd
        self.api_key = api_key

    def _invoke_agent(self, prompt: str, sandbox: Sandbox) -> AgentRun:
        env = {**os.environ}
        if self.api_key:
            env["ANTHROPIC_API_KEY"] = self.api_key  # secret enters via env, not argv
        argv = [
            self.cli_cmd,
            "-p", prompt,
            "--max-turns", str(self.turn_budget),
            # The sandbox is a throwaway, isolated copy, so the agent runs with full autonomy:
            # it must be able to run Bash (the smoke gate + git) headless. `acceptEdits` gates
            # Bash, leaving a headless agent unable to test or commit (ESSENCE Appendix D, §4E).
            "--dangerously-skip-permissions",
            "--output-format", "text",
        ]
        if self.model:
            argv += ["--model", self.model]
        started = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                cwd=sandbox.root,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.wall_clock_s,
            )
        except subprocess.TimeoutExpired as exc:
            log = (exc.stdout or "") + (exc.stderr or "") if isinstance(exc.stdout, str) else ""
            return AgentRun(
                exit_code=124, hit_wall_clock=True, log=log,
                wall_clock_s=time.monotonic() - started,
            )
        elapsed = time.monotonic() - started
        narrative = proc.stdout.strip()
        log = (proc.stdout + "\n" + proc.stderr).strip()
        # Heuristic: the CLI signals turn exhaustion in its output/exit code.
        hit_turns = "max turns" in log.lower() or "turn limit" in log.lower()
        return AgentRun(
            exit_code=proc.returncode,
            narrative=narrative,
            hit_turn_budget=hit_turns,
            log=log,
            wall_clock_s=elapsed,
        )


@dataclass
class FakeCodingAgent(BaseCodingAgent):
    """A scripted agent for tests: applies fixed file edits, then runs the real orchestration."""

    edits: dict[str, str] = field(default_factory=dict)
    run: AgentRun = field(default_factory=lambda: AgentRun(exit_code=0, narrative="fixed it"))

    def __init__(self, *, edits=None, run=None, repo="repo", smoke_command="true",
                 turn_budget=100, wall_clock_s=900, max_lines=30, max_files=2, model="fake"):
        super().__init__(repo=repo, smoke_command=smoke_command, turn_budget=turn_budget,
                         wall_clock_s=wall_clock_s, max_lines=max_lines, max_files=max_files,
                         model=model)
        self.edits = edits or {}
        self.run = run or AgentRun(exit_code=0, narrative="fixed it")

    def _invoke_agent(self, prompt: str, sandbox: Sandbox) -> AgentRun:
        if self.edits:
            sandbox.write_files(self.edits)
        return self.run
