#!/usr/bin/env python3
"""End-to-end demo + acceptance check for the closed loop. Run it after the
agent has built watchdog.py:

    python3 demo.py

It shows the buggy app logging errors, the watchdog opening a PR that fixes the
app's own code, and — after "merging" that PR into a throwaway copy — the same
app running clean. The repo's app/ is left untouched, so the demo is repeatable.
Exits non-zero if any step fails (so it doubles as the acceptance test).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "app.log")
PRS = os.path.join(ROOT, ".prs")
SLUG = "ingest-price-keyerror"


def sh(*args):
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def error_texts(log_path):
    if not os.path.exists(log_path):
        return []
    out = []
    for line in open(log_path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("level") == "ERROR":
            out.append(rec["text"])
    return out


def banner(t):
    print("\n" + "=" * 66 + f"\n{t}\n" + "=" * 66)


def main():
    # --- 1) BEFORE: the buggy app logs errors -------------------------------
    banner("1) BEFORE  —  run the buggy app; it logs errors")
    if os.path.exists(LOG):
        os.remove(LOG)
    if os.path.isdir(PRS):
        shutil.rmtree(PRS)
    sh("run_app.py")
    before = error_texts(LOG)
    for e in before:
        print("   LOG ERROR:", e)
    assert before, "expected the buggy app to log errors"

    # --- 2) WATCHDOG: read logs -> fix -> open a PR -------------------------
    banner("2) WATCHDOG  —  read the logs, draft a fix, open a PR")
    sh("watchdog.py")
    prs = sorted(os.listdir(PRS)) if os.path.isdir(PRS) else []
    print("   PRs opened:", prs or "(none)")
    assert SLUG in prs, f"expected the watchdog to open a PR '{SLUG}'"
    print("   --- PR ---")
    print(open(os.path.join(PRS, SLUG, "pr.md"), encoding="utf-8").read())

    # --- 3) MERGE into a throwaway copy and re-run --------------------------
    banner("3) MERGE the PR (you, the human) and re-run — errors should be gone")
    files = json.load(open(os.path.join(PRS, SLUG, "files.json"), encoding="utf-8"))
    work = tempfile.mkdtemp(prefix="watchdog-merge-")
    try:
        shutil.copytree(os.path.join(ROOT, "app"), os.path.join(work, "app"))
        for rel, content in files.items():
            p = os.path.join(work, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
        merged_log = os.path.join(work, "app.log")
        subprocess.run(
            [sys.executable, "-c", "import app.ingest as m; m.main()"],
            cwd=work, env=dict(os.environ, APP_LOG=merged_log), check=True,
        )
        after = error_texts(merged_log)
        print("   errors after the fix:", after or "(none)")
        assert not after, "the merged fix should have eliminated the errors"
    finally:
        shutil.rmtree(work, ignore_errors=True)

    banner("HEALED  —  the watchdog's PR fixed the code that produced the logs")


if __name__ == "__main__":
    main()
