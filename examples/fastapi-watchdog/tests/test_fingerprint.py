"""Fingerprint normalization — the highest-value test target (ESSENCE §14)."""
from watchdog.fingerprint import (
    bot_branch_name,
    changed_files,
    incident_fingerprint,
    line_fingerprint,
    normalize,
    normalize_diff,
    patch_fingerprint,
    slugify,
)


def test_two_lines_differing_only_in_volatile_detail_collide():
    a = "GET /sensors/28191/days?date=2026-05-26 failed"
    b = "GET /sensors/4/days?date=2026-05-27 failed"
    assert line_fingerprint(a) == line_fingerprint(b)


def test_genuinely_different_lines_do_not_collide():
    a = "KeyError on /items/x"
    b = "TimeoutError talking to upstream"
    assert line_fingerprint(a) != line_fingerprint(b)


def test_timestamp_masked_before_bare_date():
    # A full timestamp must be consumed before the bare-date rule can mangle it.
    out = normalize("2026-06-17 13:15:00,123 ERROR boom")
    assert "<TS>" in out
    assert "<DATE>" not in out  # the date was inside the timestamp


def test_each_volatile_category_collapses():
    pairs = [
        ("user 550e8400-e29b-41d4-a716-446655440000 in", "user 550e8400-e29b-41d4-a716-446655440001 in"),
        ("addr 0xdeadbeef here", "addr 0xcafef00d here"),
        ("from 10.0.0.1 now", "from 192.168.1.255 now"),
        ('File "/srv/app/main.py", line 63, in get', 'File "/srv/app/other.py", line 9, in get'),
        ("ts 1716700000000 done", "ts 1716700000001 done"),
        ("count 1234567 rows", "count 7654321 rows"),
    ]
    for a, b in pairs:
        assert line_fingerprint(a) == line_fingerprint(b), (a, b)


def test_normalization_is_idempotent():
    line = "2026-06-17T13:15:00Z GET http://h/items/9?x=1 -> KeyError 'k' at line 63"
    once = normalize(line)
    assert normalize(once) == once


def test_incident_fingerprint_stable_across_order_and_dups():
    fps = ["c", "a", "b", "a"]
    assert incident_fingerprint(fps) == incident_fingerprint(["a", "b", "c"])
    assert incident_fingerprint(fps) == incident_fingerprint(["b", "c", "a", "b"])


# --- diff normalization ---

_DIFF = """\
diff --git a/app/main.py b/app/main.py
index 1111111..2222222 100644
--- a/app/main.py
+++ b/app/main.py
@@ -60,3 +60,5 @@ def get_item(key: str):
     # unchanged context
-    return {"key": key, "value": STORE[key]}
+    if key not in STORE:
+        raise HTTPException(404)
"""


def test_diff_norm_stable_across_line_number_shift():
    shifted = _DIFF.replace("@@ -60,3 +60,5 @@", "@@ -120,3 +120,5 @@")
    assert patch_fingerprint(_DIFF) == patch_fingerprint(shifted)


def test_diff_norm_stable_across_reindentation():
    reindented = _DIFF.replace('+    if key not in STORE:', '+        if key not in STORE:')
    assert patch_fingerprint(_DIFF) == patch_fingerprint(reindented)


def test_diff_norm_changes_when_added_code_changes():
    other = _DIFF.replace("raise HTTPException(404)", "raise HTTPException(400)")
    assert patch_fingerprint(_DIFF) != patch_fingerprint(other)


def test_changed_files_extraction():
    assert changed_files(_DIFF) == ["app/main.py"]


def test_blob_index_dropped_from_normalized_diff():
    assert "index 1111111" not in normalize_diff(_DIFF)


# --- slug / branch ---

def test_slugify_sanitizes_and_caps():
    assert slugify("Upstream 429!! Retries") == "upstream-429-retries"
    long = slugify("a" * 50)
    assert len(long) <= 40


def test_branch_name_is_deterministic():
    fp = incident_fingerprint(["x", "y"])
    assert bot_branch_name("my slug", fp) == bot_branch_name("my slug", fp)
    assert bot_branch_name("my slug", fp).startswith("bot/my-slug-")
