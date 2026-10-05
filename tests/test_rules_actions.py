from dataclasses import replace
from datetime import date

import pytest
from market_fixtures import market, rule, rules

from doribt import CorporateAction, RuleBook


def action(**changes):
    values = dict(
        action_id="a1",
        symbol="A",
        kind="distribution",
        announced="2025-01-01",
        record_date="2025-01-03",
        ex_date="2025-01-06",
        cash_per_share="0.1",
        pay_date="2025-01-08",
        source="fictional announcement",
    )
    return CorporateAction(**(values | changes))


def test_historical_rule_selection_and_fingerprint():
    first, other = rules().periods
    first = replace(first, end="2025-01-02")
    second = replace(
        first,
        start="2025-01-03",
        end="2025-01-06",
        version="v2",
        rule=rule(stamp_duty_sell="0.00025"),
    )
    book = RuleBook((other, second, first))
    assert book.at("A", date(2025, 1, 2)).version == "v1"
    assert book.at("A", date(2025, 1, 3)).version == "v2"
    assert market(rules=book).fingerprint != market().fingerprint
    assert market(rules=book).fingerprint == market(rules=RuleBook(book.periods[::-1])).fingerprint


def test_rule_period_overlap_gap_and_missing_source():
    first, other = rules().periods
    with pytest.raises(ValueError, match="overlapping"):
        RuleBook((first, replace(first, start=first.end)))
    book = RuleBook((replace(first, end="2025-01-02"), other))
    with pytest.raises(ValueError, match="missing historical rule for A on 2025-01-03"):
        market(rules=book)
    with pytest.raises(ValueError, match="source and version"):
        replace(first, source="")
    with pytest.raises(ValueError, match="start must not follow end"):
        replace(first, start="2026-01-01")


@pytest.mark.parametrize(
    "change",
    [
        {"price_tick": 0},
        {"buy_minimum": 0},
        {"buy_step": 0.5},
        {"settlement_days": -1},
        {"settlement_days": 1.1},
        {"stamp_duty_sell": -0.01},
        {"transfer_fee": 1.1},
        {"allow_odd_lot_liquidation": 1},
    ],
)
def test_rule_parameters_reject_invalid_values(change):
    with pytest.raises(ValueError):
        rule(**change)


def test_actions_keep_dates_beyond_horizon_and_change_provenance():
    distribution = action(bonus_per_share="1.5", share_listing_date="2025-01-09")
    data = market(actions=[distribution])
    assert distribution.pay_date == date(2025, 1, 8)
    assert distribution.share_listing_date == date(2025, 1, 9)
    assert data.fingerprint != market().fingerprint
    assert data.fingerprint != market(actions=[replace(distribution, source="other")]).fingerprint
    with pytest.raises(ValueError, match="duplicate corporate-action id"):
        market(actions=[distribution, distribution])
    with pytest.raises(ValueError, match="unknown corporate-action symbol"):
        market(actions=[replace(distribution, symbol="unknown")])


@pytest.mark.parametrize(
    "change,match",
    [
        ({"action_id": ""}, "action_id"),
        ({"kind": "split_unknown"}, "unknown"),
        ({"record_date": "2025-01-06"}, "action dates"),
        ({"announced": "2025-01-04"}, "action dates"),
        ({"pay_date": None}, "pay_date is required"),
        ({"pay_date": "2025-01-03"}, "must not precede"),
        ({"cash_per_share": 0}, "requires cash or bonus"),
        ({"bonus_per_share": 0.5}, "share_listing_date is required"),
        ({"bonus_per_share": -0.5}, "outside supported bounds"),
        ({"share_listing_date": "2025-01-06"}, "share_listing_date is required"),
        ({"kind": "rights_issue"}, "belong to distributions"),
    ],
)
def test_action_facts_do_not_guess_missing_entitlements(change, match):
    with pytest.raises(ValueError, match=match):
        action(**change)


def test_unsupported_actions_remain_explicit_facts():
    rights = action(kind="rights_issue", cash_per_share=0, pay_date=None)
    assert market(actions=[rights]).actions[0].kind == "rights_issue"
