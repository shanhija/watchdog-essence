"""LLM budget rate limiter (ESSENCE §8) and boot invariants (ESSENCE §14)."""
import pytest

from watchdog.budget import LLMBudget
from watchdog.config import BootError, Config, Rule, validate_boot


def test_hourly_budget_blocks_then_recovers():
    t = [0.0]
    b = LLMBudget(hourly=2, daily=100, now_fn=lambda: t[0])
    assert b.try_charge()
    assert b.try_charge()
    assert not b.try_charge()  # hourly exhausted
    t[0] += 3601  # an hour later
    assert b.try_charge()


def test_daily_budget_blocks_independently():
    t = [0.0]
    b = LLMBudget(hourly=100, daily=3, now_fn=lambda: t[0])
    for _ in range(3):
        assert b.try_charge()
        t[0] += 1800  # spread across the day, hourly never bites
    assert not b.try_charge()  # daily exhausted


def test_try_charge_does_not_charge_when_exhausted():
    b = LLMBudget(hourly=1, daily=1, now_fn=lambda: 0.0)
    assert b.try_charge()
    assert not b.try_charge()
    assert not b.available()


def test_boot_fails_without_api_key():
    cfg = Config(rules=[Rule("r", "{}")], anthropic_api_key="")
    with pytest.raises(BootError, match="ANTHROPIC_API_KEY"):
        validate_boot(cfg)


def test_boot_fails_auto_pr_on_without_code_host():
    cfg = Config(rules=[Rule("r", "{}")], anthropic_api_key="k",
                 auto_pr_enabled=True, code_host="none")
    with pytest.raises(BootError, match="nothing can open a PR"):
        validate_boot(cfg)


def test_boot_fails_github_without_token():
    cfg = Config(rules=[Rule("r", "{}")], anthropic_api_key="k",
                 auto_pr_enabled=True, code_host="github", github_repo="o/r", code_host_token="")
    with pytest.raises(BootError, match="GITHUB_REPO / token missing"):
        validate_boot(cfg)


def test_boot_ok_with_defaults():
    cfg = Config(rules=[Rule("r", "{}")], anthropic_api_key="k")  # auto-PR off by default
    validate_boot(cfg)  # no raise
