#!/usr/bin/env python3
"""End-to-end demo + acceptance check for the closed loop — colored and paced
for screen recording, so a single run tells the whole story (problem → the
prompt → the fix → healed).

    python3 demo.py             # colored + paced, good for recording a GIF
    DEMO_FAST=1 python3 demo.py  # no pauses (quick check / acceptance)
    NO_COLOR=1 python3 demo.py   # plain text

Run it after the agent has built watchdog.py. The repo's app/ is left untouched,
so it's repeatable. Exits non-zero on any failure (so it doubles as the test).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "app.log")
PRS = os.path.join(ROOT, ".prs")
SLUG = "ingest-price-keyerror"
FAST = bool(os.environ.get("DEMO_FAST"))
PROMPT = "Build me a service from this essence in this context."

# --- color ---------------------------------------------------------------
_COLOR = (bool(os.environ.get("FORCE_COLOR")) or sys.stdout.isatty()) and not os.environ.get("NO_COLOR")


def _c(code):
    return (lambda s: f"\033[{code}m{s}\033[0m") if _COLOR else (lambda s: s)


bold = _c("1")
dim = _c("2")
red = _c("31")
green = _c("32")
cyan = _c("36")
brgreen = _c("92")
brred = _c("91")


def chip(text, bg):
    return f"\033[1;97;{bg}m {text} \033[0m" if _COLOR else f"[{text}]"


def rule(width=66):
    return dim("─" * width)


def pause(seconds):
    if not FAST:
        time.sleep(seconds)


def type_out(text, code="1;97", delay=0.022):
    if _COLOR:
        sys.stdout.write(f"\033[{code}m")
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        if not FAST:
            time.sleep(delay)
    if _COLOR:
        sys.stdout.write("\033[0m")
    sys.stdout.write("\n")
    sys.stdout.flush()


def step(n, title, bg):
    print()
    print(f"{chip(n, bg)} {bold(title)}")
    print(rule())


def error_texts(log_path):
    if not os.path.exists(log_path):
        return []
    out = []
    for line in open(log_path, encoding="utf-8"):
        line = line.strip()
        if line and json.loads(line).get("level") == "ERROR":
            out.append(json.loads(line)["text"])
    return out


def parse_pr(path):
    raw = open(path, encoding="utf-8").read()
    head = [l for l in raw.split("```diff", 1)[0].splitlines() if l.strip()]
    title = head[0].lstrip("#").strip() if head else ""
    body = head[1].strip() if len(head) > 1 else ""
    diff = ""
    if "```diff" in raw:
        diff = raw.split("```diff", 1)[1].split("\n", 1)[1].rsplit("```", 1)[0]
    return title, body, diff


def render_diff(diff):
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "diff --git")):
            out = bold(line)
        elif line.startswith("@@"):
            out = cyan(line)
        elif line.startswith("+"):
            out = green(line)
        elif line.startswith("-"):
            out = red(line)
        else:
            out = dim(line)
        print("   " + out)
        pause(0.03)


def main():
    print()
    print("   " + bold(cyan("watchdog-essence")) + dim("  ·  python context"))

    # --- 1) BEFORE ----------------------------------------------------------
    step(1, "BEFORE  —  run the buggy app; it logs errors", 41)
    if os.path.exists(LOG):
        os.remove(LOG)
    if os.path.isdir(PRS):
        shutil.rmtree(PRS)
    subprocess.run([sys.executable, "run_app.py"], cwd=ROOT, check=True)
    before = error_texts(LOG)
    for e in before:
        print("   " + brred("✗") + " " + e)
        pause(0.3)
    assert before, "expected the buggy app to log errors"
    pause(0.9)

    # --- 2) THE PROMPT ------------------------------------------------------
    step(2, "THE PROMPT  —  hand your coding agent the essence + one line", 45)
    pause(0.4)
    print()
    print("   " + dim("So you tell your coding agent (Claude, Cursor, …):"))
    print()
    sys.stdout.write("   " + dim("you") + " " + _c("35")("▸") + " ")
    type_out(f'"{PROMPT}"')
    pause(0.5)
    print()
    print("   " + dim("→ a coding agent reads ") + cyan("ESSENCE.md") + dim(" + ") + cyan("AGENTS.md")
          + dim(" and writes ") + cyan("watchdog.py") + dim("."))
    print("   " + dim("  (try it yourself — here we just run the watchdog it produces.)"))
    pause(0.9)

    # --- 3) WATCHDOG --------------------------------------------------------
    step(3, "WATCHDOG  —  read the logs, draft a fix, open a PR", 44)
    print("   " + dim("running watchdog.py …"))
    proc = subprocess.run([sys.executable, "watchdog.py"], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(brred("watchdog.py isn't built yet — see AGENTS.md "
                               "(or `cp watchdog.reference.py watchdog.py` to record)."))
    prs = sorted(os.listdir(PRS)) if os.path.isdir(PRS) else []
    assert SLUG in prs, f"expected the watchdog to open a PR '{SLUG}'"
    title, body, diff = parse_pr(os.path.join(PRS, SLUG, "pr.md"))
    pause(0.4)
    print()
    print("   " + green("✓") + " " + bold("watchdog opened a pull request") + dim(f"  ({SLUG})"))
    if body:
        print("   " + dim("  root cause: ") + body)
    print()
    print("   " + dim("patch ") + rule(58))
    pause(1.0)
    render_diff(diff)
    print("   " + rule(64))
    print("   " + dim("note — here, triage + the fix are deterministic stand-ins (no API key)."))
    pause(1.0)

    # --- 4) MERGE + AFTER ---------------------------------------------------
    step(4, "MERGE the PR (you, the human) and re-run", 42)
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
        if after:
            for e in after:
                print("   " + brred("✗ ") + e)
        else:
            print("   " + green("✓ no errors — the app runs clean."))
        assert not after, "the merged fix should have eliminated the errors"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    pause(0.7)

    # --- finale -------------------------------------------------------------
    print()
    print(green("─" * 66))
    print("   " + brgreen(bold("✓  HEALED")) + "   "
          + dim("the watchdog's PR fixed the code that produced the logs."))
    print(green("─" * 66))
    print("   " + dim("real here: the essence, the pipeline, the sandboxed test, the diff."))
    print("   " + dim("stand-ins here: the model (triage) + the coding agent — swap in your own."))


if __name__ == "__main__":
    main()
