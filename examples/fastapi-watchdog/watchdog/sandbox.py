"""Sandbox — the ephemeral, isolated copy of production (ESSENCE §4E, Appendix I).

The watchdog is a deployed service with **no working checkout of its own**, so it
*provisions* a pristine, isolated copy per fix attempt. Here that copy is a fresh tree
copied into a throwaable tempdir and `git init`-ed (so diffs work even though the source
repo isn't itself a git repo), carrying the app's full runtime + test deps so the smoke
gate is real. The non-negotiables are *pristine + isolated*.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Optional, Protocol

# Directories never copied into a sandbox (the watchdog's own state, venvs, vcs).
_EXCLUDE = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "watchdog_data", "node_modules"}


class Sandbox(Protocol):
    def materialize(self) -> None: ...
    def write_files(self, files: dict[str, str]) -> None: ...
    def run_tests(self) -> tuple[bool, str]: ...
    def diff(self) -> str: ...
    def cleanup(self) -> None: ...
    @property
    def root(self) -> str: ...


def _git(cwd: str, *args: str, env: Optional[dict] = None,
         timeout: Optional[float] = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, "GIT_AUTHOR_NAME": "watchdog", "GIT_AUTHOR_EMAIL": "watchdog@localhost",
                "GIT_COMMITTER_NAME": "watchdog", "GIT_COMMITTER_EMAIL": "watchdog@localhost"}
    if env:
        full_env.update(env)
    return subprocess.run(
        ["git", *args], cwd=cwd, env=full_env, capture_output=True, text=True, timeout=timeout
    )


class LocalGitSandbox:
    """Copy the repo tree into a tempdir, git-init it, cut a bot branch off prod."""

    def __init__(
        self,
        source_root: str,
        *,
        smoke_command: str,
        branch: str,
        prod_branch: str = "main",
    ) -> None:
        self.source_root = os.path.abspath(source_root)
        self.smoke_command = smoke_command
        self.branch = branch
        self.prod_branch = prod_branch
        self._root: Optional[str] = None

    @property
    def root(self) -> str:
        if self._root is None:
            raise RuntimeError("sandbox not materialized")
        return self._root

    def materialize(self) -> None:
        tmp = tempfile.mkdtemp(prefix="wd-sandbox-")
        shutil.copytree(
            self.source_root,
            tmp,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(*_EXCLUDE),
        )
        self._root = tmp
        _git(tmp, "init", "-q")
        # Ignore tooling artifacts the coding agent may drop into the sandbox during its run
        # (its own config/cache dirs, venvs, __pycache__) so they never pollute the fix diff.
        # Written to .git/info/exclude (not a tracked .gitignore) so it doesn't show in the diff.
        with open(os.path.join(tmp, ".git", "info", "exclude"), "a", encoding="utf-8") as f:
            f.write("\n# watchdog: tooling artifacts (never part of a fix diff)\n")
            f.write("\n".join((
                ".venv/", "venv/", "__pycache__/", "*.pyc", ".pytest_cache/",
                "watchdog_data/", "node_modules/", ".serena/", ".claude/",
                ".mypy_cache/", ".ruff_cache/",
            )) + "\n")
        _git(tmp, "checkout", "-q", "-b", self.prod_branch)
        _git(tmp, "add", "-A")
        _git(tmp, "commit", "-q", "-m", "watchdog: pristine production snapshot")
        # The agent only ever works on its own bot branch.
        _git(tmp, "checkout", "-q", "-b", self.branch)

    def write_files(self, files: dict[str, str]) -> None:
        for rel, content in files.items():
            path = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)

    def run_tests(self) -> tuple[bool, str]:
        proc = subprocess.run(
            self.smoke_command,
            cwd=self.root,
            shell=True,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": self.root},
        )
        return proc.returncode == 0, (proc.stdout + proc.stderr)

    def commit(self, message: str) -> None:
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", message)

    def diff(self) -> str:
        # Diff the bot branch against the pristine prod snapshot.
        proc = _git(self.root, "diff", f"{self.prod_branch}...HEAD")
        if proc.stdout.strip():
            return proc.stdout
        # Fall back to the working-tree diff if nothing was committed.
        return _git(self.root, "diff").stdout

    def cleanup(self) -> None:
        if self._root and os.path.isdir(self._root):
            shutil.rmtree(self._root, ignore_errors=True)
            self._root = None
