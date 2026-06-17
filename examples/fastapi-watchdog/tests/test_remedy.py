"""Remedy dedup cascade (ESSENCE §4G, §6.3)."""
from watchdog.codehost import FakeCodeHost
from watchdog.models import PullRequest
from watchdog.remedy import COMPLEMENTARY, DUPLICATE, NEW, SUPERSEDE, remedy_dedup

DIFF_A = """\
diff --git a/app/main.py b/app/main.py
--- a/app/main.py
+++ b/app/main.py
@@ -60,2 +60,3 @@
+    if key not in STORE:
+        raise HTTPException(404)
"""

DIFF_B = """\
diff --git a/app/other.py b/app/other.py
--- a/app/other.py
+++ b/app/other.py
@@ -1,2 +1,3 @@
+    pass
"""


class FakeAdjudicator:
    def __init__(self, verdict):
        self.verdict = verdict
        self.calls = 0

    def adjudicate(self, new_diff, existing_diff):
        self.calls += 1
        return self.verdict


def test_no_open_prs_opens_fresh():
    decision = remedy_dedup(DIFF_A, FakeCodeHost(), base_branch="integration")
    assert decision.action == NEW


def test_identical_diff_is_duplicate_via_hash_no_llm():
    host = FakeCodeHost([PullRequest(number=7, url="u", branch="bot/x-1", base="integration", diff=DIFF_A)])
    adj = FakeAdjudicator("unrelated")
    decision = remedy_dedup(DIFF_A, host, base_branch="integration", adjudicator=adj)
    assert decision.action == DUPLICATE
    assert decision.target_pr == 7
    assert adj.calls == 0  # tier 1 short-circuits the LLM


def test_non_overlapping_file_skips_llm_and_opens_fresh():
    host = FakeCodeHost([PullRequest(number=7, url="u", branch="bot/x-1", base="integration", diff=DIFF_B)])
    adj = FakeAdjudicator("duplicate")
    decision = remedy_dedup(DIFF_A, host, base_branch="integration", adjudicator=adj)
    assert decision.action == NEW
    assert adj.calls == 0  # no shared changed file → not a candidate


def test_overlapping_file_uses_adjudicator_supersede():
    overlapping = DIFF_A.replace("raise HTTPException(404)", "raise HTTPException(404)  # tweak")
    host = FakeCodeHost([PullRequest(number=9, url="u9", branch="bot/x-1", base="integration",
                                     diff=overlapping)])
    adj = FakeAdjudicator("supersedes")
    decision = remedy_dedup(DIFF_A, host, base_branch="integration", adjudicator=adj)
    assert decision.action == SUPERSEDE
    assert decision.target_pr == 9
    assert adj.calls == 1


def test_complementary_verdict():
    overlapping = DIFF_A.replace("404", "400")
    host = FakeCodeHost([PullRequest(number=9, url="u9", branch="bot/x-1", base="integration",
                                     diff=overlapping)])
    decision = remedy_dedup(DIFF_A, host, base_branch="integration",
                            adjudicator=FakeAdjudicator("complementary"))
    assert decision.action == COMPLEMENTARY


def test_fails_open_on_error():
    class Boom:
        def list_open_bot_prs(self, *a, **k):
            raise RuntimeError("code host down")

    decision = remedy_dedup(DIFF_A, Boom(), base_branch="integration")
    assert decision.action == NEW
    assert decision.verdict == "error-fail-open"
