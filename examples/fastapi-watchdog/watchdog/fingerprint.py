"""Fingerprinting — the three dedup keys (ESSENCE §5, Appendix F).

All three are "normalize, then hash". The normalization is the whole game: it must
erase *volatile* detail while preserving *identity*. Order matters (mask the full
timestamp before the bare date, UUIDs before digit-runs, etc.).
"""
from __future__ import annotations

import hashlib
import re

# Normalization rules, applied IN ORDER (most-specific first). Each is (regex, replacement).
# The placeholders stay human-readable (<TS>, <PATH>, …) which helps debugging.
_NORMALIZE_RULES: list[tuple[re.Pattern[str], str]] = [
    # 1. ISO-8601 timestamp (with optional time, ms/us, tz). Mask before the bare date.
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<TS>"),
    # 2. bare ISO date
    (re.compile(r"\d{4}-\d{2}-\d{2}"), "<DATE>"),
    # 3. UUID (before any digit-run rule)
    (re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"), "<UUID>"),
    # 4. URL — keep scheme+host, mask path+query
    (re.compile(r"(https?://[^/\s]+)/\S*"), r"\1/<PATH>"),
    # 5a. bare absolute/request path (>= 2 segments), with any query
    (re.compile(r"/[^\s/]+(?:/[^\s]*)+"), "<PATH>"),
    # 5b. relative path with a file extension (e.g. app/main.py)
    (re.compile(r"\b[\w.-]+(?:/[\w.-]+)+\.\w+"), "<PATH>"),
    # 6. hex address
    (re.compile(r"0x[0-9a-fA-F]+"), "<HEX>"),
    # 7. File "...", line N  (robust even if the path was already masked to <PATH>)
    (re.compile(r'File "[^"]*", line \d+'), 'File "<F>", line <N>'),
    # 8. bare "line N"
    (re.compile(r"\bline \d+"), "line <N>"),
    # 9. IPv4
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "<IP>"),
    # 10. epoch number (10-13 digits)
    (re.compile(r"\b\d{10,13}\b"), "<EPOCH>"),
    # 11. long digit run (>= 6 digits) — ids, counts
    (re.compile(r"\d{6,}"), "<NUM>"),
]

_WHITESPACE = re.compile(r"\s+")


def normalize(line: str) -> str:
    """Strip, apply the rules in order, then collapse whitespace runs to one space."""
    out = line.strip()
    for pattern, repl in _NORMALIZE_RULES:
        out = pattern.sub(repl, out)
    return _WHITESPACE.sub(" ", out).strip()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def line_fingerprint(line: str) -> str:
    """line-level dedup key — sha256(normalize(line))."""
    return _sha256(normalize(line))


def incident_fingerprint(line_fingerprints: list[str]) -> str:
    """incident-level dedup key (symptom identity).

    Hash the sorted, de-duplicated set of line fingerprints. Sorting + set-dedup makes
    it stable across the model re-ordering or repeating lines.
    """
    unique_sorted = sorted(set(line_fingerprints))
    return _sha256("\n".join(unique_sorted))


# --- diff / remedy fingerprinting -------------------------------------------------

_BLOB_INDEX = re.compile(r"^index [0-9a-f]+\.\.[0-9a-f]+")
_HUNK_HEADER = re.compile(r"^@@ .* @@.*$")


def normalize_diff(diff: str) -> str:
    """Normalize a unified diff for the patch fingerprint (Appendix F).

    Keep file headers and added/removed lines (inner whitespace collapsed); drop the
    blob-index lines, reduce each hunk header to a bare ``@@``, and drop context
    (unchanged) lines. Stable across reindentation and line-number shifts; *not* across
    renamed locals or reworded comments (those near-misses are the LLM adjudicator's job).
    """
    kept: list[str] = []
    for raw in diff.splitlines():
        if raw.startswith("diff --git ") or raw.startswith("--- ") or raw.startswith("+++ "):
            kept.append(_WHITESPACE.sub(" ", raw).strip())
        elif _BLOB_INDEX.match(raw):
            continue
        elif _HUNK_HEADER.match(raw):
            kept.append("@@")
        elif raw.startswith("+") or raw.startswith("-"):
            kept.append(_WHITESPACE.sub(" ", raw).strip())
        # else: context / unchanged line → drop
    return "\n".join(kept)


def patch_fingerprint(diff: str) -> str:
    """fix-level dedup key (remedy identity) — sha256(normalize_diff(diff))."""
    return _sha256(normalize_diff(diff))


_CHANGED_FILE = re.compile(r"^\+\+\+ b/(.+)$")


def changed_files(diff: str) -> list[str]:
    """Extract the set of changed file paths from a unified diff (the ``+++ b/...`` lines)."""
    files: list[str] = []
    for raw in diff.splitlines():
        m = _CHANGED_FILE.match(raw)
        if m and m.group(1) != "/dev/null":
            files.append(m.group(1))
    return files


# --- slug / branch naming (Appendix E) --------------------------------------------

_SLUG_INVALID = re.compile(r"[^a-z0-9-]+")
_SLUG_DASHES = re.compile(r"-+")


def slugify(text: str, *, cap: int = 40) -> str:
    """lowercase · non-[a-z0-9-] → '-' · collapse '--' · trim '-' · cap on a '-' boundary."""
    out = _SLUG_INVALID.sub("-", text.lower())
    out = _SLUG_DASHES.sub("-", out).strip("-")
    if len(out) > cap:
        out = out[:cap].rsplit("-", 1)[0] if "-" in out[:cap] else out[:cap]
        out = out.strip("-")
    return out or "incident"


def bot_branch_name(slug: str, incident_fp: str) -> str:
    """Deterministic bot branch: bot/<slug>-<incident_fingerprint[:8]> (idempotent)."""
    return f"bot/{slugify(slug)}-{incident_fp[:8]}"
