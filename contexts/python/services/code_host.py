"""Code host — opens pull requests. This fake records each PR under `.prs/<slug>/`
(a human-readable patch + the patched file contents, so a reviewer can merge it).
Swap for your git host's PR API (ESSENCE §4H)."""
import json
import os


class LocalCodeHost:
    def __init__(self, prs_dir: str) -> None:
        self.prs_dir = prs_dir

    def open_pr(self, slug: str, title: str, body: str, diff: str, files: dict) -> str:
        d = os.path.join(self.prs_dir, slug)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "pr.md"), "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n{body}\n\n```diff\n{diff}```\n")
        with open(os.path.join(d, "files.json"), "w", encoding="utf-8") as f:
            json.dump(files, f)
        return f"file://{d}"

    def list_prs(self) -> list[str]:
        if not os.path.isdir(self.prs_dir):
            return []
        return sorted(n for n in os.listdir(self.prs_dir) if os.path.isdir(os.path.join(self.prs_dir, n)))
