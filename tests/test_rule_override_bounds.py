"""自定义规则闭区间在最早及最晚日期仍能正确覆盖。"""

from dataclasses import replace
from datetime import date, timedelta

import pytest
from engine_fixtures import data_for

from doribt import RuleBook, RuleOverride


def override(start, end, settlement, *, symbol="A"):
    return RuleOverride(
        symbol=symbol,
        start=start,
        end=end,
        changes={"settlement_days": settlement},
        reason="极值日期回归",
        source="synthetic scenario",
        version="1",
    )


def test_overrides_preserve_both_extreme_days_and_middle_interval():
    base = replace(data_for([10]).rules.periods[0], start=date.min, end=date.max)
    book = RuleBook((base,)).with_overrides(
        [override(date.min, date.min, 0), override(date.max, date.max, 2)]
    )
    assert [(period.start, period.end, period.rule.settlement_days) for period in book.periods] == [
        (date.min, date.min, 0),
        (date.min + timedelta(days=1), date.max - timedelta(days=1), 1),
        (date.max, date.max, 2),
    ]
    assert book.at("A", date.min).rule.settlement_days == 0
    assert book.at("A", date(2025, 1, 2)).rule.settlement_days == 1
    assert book.at("A", date.max).rule.settlement_days == 2


def test_unrelated_open_ended_security_does_not_break_finite_override():
    base = data_for([10]).rules.periods[0]
    other = replace(base, symbol="B", end=date.max)
    book = RuleBook((base, other)).with_overrides([override(base.start, base.end, 0)])
    assert book.at("A", date(2025, 1, 2)).rule.settlement_days == 0
    assert book.at("B", date.max) == other


def test_full_open_ended_override_can_be_chained_with_specific_profile_precedence():
    base = replace(data_for([10]).rules.periods[0], start=date.min, end=date.max)
    broad = RuleOverride(
        profile="custom",
        start=date.min,
        end=date.max,
        changes={"settlement_days": 0},
        reason="全区间情景",
        source="synthetic scenario",
        version="1",
    )
    book = RuleBook((base,), profiles=(("A", "custom"),)).with_overrides([broad])
    final = book.with_overrides([override(date.max, date.max, 2)])
    assert final.at("A", date.max - timedelta(days=1)).rule.settlement_days == 0
    assert final.at("A", date.max).rule.settlement_days == 2
    with pytest.raises(ValueError, match="conflicting overrides"):
        final.with_overrides([override(date.max, date.max, 1)])


def test_gap_near_maximum_date_is_still_rejected():
    base = data_for([10]).rules.periods[0]
    early = replace(base, start=date.max - timedelta(days=2), end=date.max - timedelta(days=2))
    late = replace(base, start=date.max, end=date.max)
    with pytest.raises(ValueError, match="outside covered"):
        RuleBook((early, late)).with_overrides([override(early.start, date.max, 0)])
