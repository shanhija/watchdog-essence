"""Fix-status classification + the gate (ESSENCE §11, §9, Appendix E)."""
import pytest

from watchdog import status as st


@pytest.mark.parametrize(
    "kw,expected",
    [
        (dict(exit_code=0, hit_turn_budget=True, hit_wall_clock=False, diff_empty=False,
              smoke_passed=True, has_narrative=True), st.TURNS_EXHAUSTED),
        (dict(exit_code=0, hit_turn_budget=False, hit_wall_clock=True, diff_empty=False,
              smoke_passed=True, has_narrative=True), st.TIMED_OUT),
        (dict(exit_code=1, hit_turn_budget=False, hit_wall_clock=False, diff_empty=False,
              smoke_passed=True, has_narrative=True), st.CRASHED),
        (dict(exit_code=0, hit_turn_budget=False, hit_wall_clock=False, diff_empty=True,
              smoke_passed=False, has_narrative=True), st.DEFERRED),
        (dict(exit_code=0, hit_turn_budget=False, hit_wall_clock=False, diff_empty=True,
              smoke_passed=False, has_narrative=False), st.DIFF_EMPTY),
        (dict(exit_code=0, hit_turn_budget=False, hit_wall_clock=False, diff_empty=False,
              smoke_passed=False, has_narrative=True), st.SMOKE_FAILED),
        (dict(exit_code=0, hit_turn_budget=False, hit_wall_clock=False, diff_empty=False,
              smoke_passed=True, has_narrative=True), st.SUCCEEDED),
    ],
)
def test_classify_status_table(kw, expected):
    assert st.classify_status(**kw) == expected


def test_turn_budget_beats_everything():
    # order matters: turns_exhausted is checked before crashed
    assert st.classify_status(
        exit_code=1, hit_turn_budget=True, hit_wall_clock=True,
        diff_empty=True, smoke_passed=False, has_narrative=False,
    ) == st.TURNS_EXHAUSTED


def test_is_actionable():
    assert st.is_actionable("high", "high")
    assert st.is_actionable("low", "medium")
    assert not st.is_actionable("noop", "high")  # benign
    assert not st.is_actionable("high", "low")  # not confident enough


def test_should_open_pr_requires_all_conditions():
    base = dict(severity="high", confidence="high", status=st.SUCCEEDED)
    assert st.should_open_pr(**base, auto_pr_enabled=True)
    assert not st.should_open_pr(**base, auto_pr_enabled=False)  # auto-PR off
    assert not st.should_open_pr(severity="high", confidence="high", status=st.SMOKE_FAILED,
                                 auto_pr_enabled=True)
    assert not st.should_open_pr(severity="noop", confidence="high", status=st.SUCCEEDED,
                                 auto_pr_enabled=True)  # not actionable


def test_strict_pr_gate():
    assert not st.should_open_pr(severity="low", confidence="high", status=st.SUCCEEDED,
                                 auto_pr_enabled=True, strict=True)  # low severity blocked
    assert st.should_open_pr(severity="medium", confidence="high", status=st.SUCCEEDED,
                             auto_pr_enabled=True, strict=True)
