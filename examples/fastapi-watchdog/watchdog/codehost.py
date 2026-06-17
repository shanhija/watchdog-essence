"""Code host port + adapters (ESSENCE §4H, Appendix B).

Infrastructure role — many non-AI implementations, kept abstract. This environment has
no code host wired up for automation, so the default is ``NullCodeHost`` (auto-PR off:
the diff is attached to the report and also written to a patch file on disk). A GitHub
adapter is provided for when the operator supplies a repo + token.

Delivery is over the network with a token from the environment; the service has no local
clone and no interactive CLI (`gh`).
"""
from __future__ import annotations

import os
from typing import Optional, Protocol

from .models import PullRequest


class PushRejected(RuntimeError):
    """Raised when a remote branch diverged (a human touched it) — never overwrite it."""


class CodeHost(Protocol):
    def open_pr(self, *, branch: str, base: str, title: str, body: str, diff: str) -> str: ...
    def comment(self, pr_number: int, text: str) -> None: ...
    def list_open_bot_prs(self, branch_prefix: str, base: str, limit: int = 20) -> list[PullRequest]: ...
    def get_pr_diff(self, pr_number: int) -> str: ...


class NullCodeHost:
    """No code host: write the patch to disk and return a file:// 'url'. Never opens a PR.

    This is the safe default for an environment with no automation-wired code host —
    you still get the value (a tested draft fix on disk + in the report) with zero branch
    risk while trust is built (ESSENCE §9).
    """

    def __init__(self, patches_dir: str = "watchdog_data/patches") -> None:
        self.patches_dir = patches_dir
        os.makedirs(patches_dir, exist_ok=True)

    def open_pr(self, *, branch: str, base: str, title: str, body: str, diff: str) -> str:
        path = os.path.join(self.patches_dir, f"{branch.replace('/', '_')}.patch")
        with open(path, "w") as f:
            f.write(f"# {title}\n# base: {base}\n#\n{body}\n\n{diff}")
        return f"file://{os.path.abspath(path)}"

    def comment(self, pr_number: int, text: str) -> None:  # no PRs to comment on
        pass

    def list_open_bot_prs(self, branch_prefix: str, base: str, limit: int = 20) -> list[PullRequest]:
        return []

    def get_pr_diff(self, pr_number: int) -> str:
        return ""


class GitHubCodeHost:
    """Opens PRs into the review branch via the GitHub REST API (branch push + PR open).

    Pushes the bot branch with a compare-and-swap guarantee: if the remote branch diverged,
    refuse to overwrite and raise ``PushRejected`` (ESSENCE §6 fail-safe, §13).
    """

    def __init__(self, repo: str, token: str, *, branch_prefix: str = "bot/") -> None:
        import httpx

        self._httpx = httpx
        self.repo = repo  # "owner/repo"
        self.token = token
        self.branch_prefix = branch_prefix
        self.api = "https://api.github.com"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        }

    def open_pr(self, *, branch: str, base: str, title: str, body: str, diff: str) -> str:
        # NOTE: the orchestrator pushes the bot branch (git push with --force-with-lease,
        # done in deliver.py); this opens the PR over the API.
        resp = self._httpx.post(
            f"{self.api}/repos/{self.repo}/pulls",
            headers=self._headers(),
            json={"title": title, "head": branch, "base": base, "body": body},
            timeout=30.0,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"open_pr failed: {resp.status_code} {resp.text}")
        return resp.json()["html_url"]

    def comment(self, pr_number: int, text: str) -> None:
        self._httpx.post(
            f"{self.api}/repos/{self.repo}/issues/{pr_number}/comments",
            headers=self._headers(),
            json={"body": text},
            timeout=30.0,
        )

    def list_open_bot_prs(self, branch_prefix: str, base: str, limit: int = 20) -> list[PullRequest]:
        resp = self._httpx.get(
            f"{self.api}/repos/{self.repo}/pulls",
            headers=self._headers(),
            params={"state": "open", "base": base, "per_page": limit},
            timeout=30.0,
        )
        resp.raise_for_status()
        out: list[PullRequest] = []
        for pr in resp.json():
            head_ref = pr["head"]["ref"]
            if head_ref.startswith(branch_prefix):
                out.append(
                    PullRequest(
                        number=pr["number"],
                        url=pr["html_url"],
                        branch=head_ref,
                        base=pr["base"]["ref"],
                    )
                )
        return out

    def get_pr_diff(self, pr_number: int) -> str:
        resp = self._httpx.get(
            f"{self.api}/repos/{self.repo}/pulls/{pr_number}",
            headers={**self._headers(), "Accept": "application/vnd.github.v3.diff"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.text


class FakeCodeHost:
    """In-memory code host for tests — records actions, never touches the network."""

    def __init__(self, existing: Optional[list[PullRequest]] = None) -> None:
        self.existing = existing or []
        self.opened: list[dict] = []
        self.comments: list[tuple[int, str]] = []
        self._next = 100 + len(self.existing)

    def open_pr(self, *, branch: str, base: str, title: str, body: str, diff: str) -> str:
        self._next += 1
        url = f"https://example.test/pr/{self._next}"
        self.opened.append({"branch": branch, "base": base, "title": title, "body": body,
                            "diff": diff, "url": url})
        return url

    def comment(self, pr_number: int, text: str) -> None:
        self.comments.append((pr_number, text))

    def list_open_bot_prs(self, branch_prefix: str, base: str, limit: int = 20) -> list[PullRequest]:
        return [pr for pr in self.existing if pr.branch.startswith(branch_prefix) and pr.base == base][:limit]

    def get_pr_diff(self, pr_number: int) -> str:
        for pr in self.existing:
            if pr.number == pr_number:
                return pr.diff
        return ""
