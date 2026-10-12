from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from engine_fixtures import data_for

from doribt import Backtest, RuleBook, RuleOverride, china_rules


def override(**kwargs):
    return RuleOverride(
        **(
            dict(
                symbol="A",
                start="2023-08-25",
                end="2023-08-29",
                changes={"settlement_days": 0},
                reason="日内交易情景",
                source="user scenario",
                version="test-1",
            )
            | kwargs
        )
    )


def rules(items=()):
    return china_rules(
        {"A": "sse_main", "B": "sse_main"}, start="2023-08-24", end="2023-08-30", overrides=items
    )


def test_symbol_date_override_preserves_official_fees_and_other_security():
    book = rules([override()])
    for session, delay, stamp in [
        ("2023-08-24", 1, ".001"),
        ("2023-08-25", 0, ".001"),
        ("2023-08-28", 0, ".0005"),
        ("2023-08-29", 0, ".0005"),
        ("2023-08-30", 1, ".0005"),
    ]:
        period = book.at("A", date.fromisoformat(session))
        assert period.rule.settlement_days == delay
        assert period.rule.stamp_duty_sell == Decimal(stamp)
        assert book.at("B", date.fromisoformat(session)).rule.settlement_days == 1
    assert rules().at("A", date(2023, 8, 25)).rule.settlement_days == 1


def test_profile_symbol_precedence_order_independence_and_chained_calls():
    broad = override(symbol=None, profile="sse_main", changes={"settlement_days": 0})
    specific = override(changes={"settlement_days": 1})
    first, second = rules([broad, specific]), rules([specific, broad])
    assert first.periods == second.periods
    assert first.provenance() == second.provenance()
    assert first.at("A", date(2023, 8, 28)).rule.settlement_days == 1
    assert first.at("B", date(2023, 8, 28)).rule.settlement_days == 0
    assert rules([specific]).with_overrides([broad]).periods == first.periods


def test_overrides_are_immutable_and_metadata_changes_fingerprint_even_for_same_value():
    changes = {"settlement_days": 0}
    item = override(changes=changes)
    changes["settlement_days"] = 1
    assert item.changes["settlement_days"] == 0
    with pytest.raises(TypeError):
        item.changes["settlement_days"] = 1
    data = data_for([10, 10, 10])
    item = override(start=data.sessions[0], end=data.sessions[-1], changes={"settlement_days": 1})
    amended = replace(data, rules=data.rules.with_overrides([item]))
    assert data.fingerprint != amended.fingerprint
    info = Backtest(amended).run(lambda ctx: None).run_info.to_dict()["data"]
    assert info["rule_provenance"]["overrides"][0]["reason"] == "日内交易情景"
    assert info["rules"][0]["version"] != data.rules.periods[0].version
    record = item.to_dict()
    record["changes"]["settlement_days"] = 0
    assert item.changes["settlement_days"] == 1


@pytest.mark.parametrize(
    "change",
    [
        {"changes": {}},
        {"changes": {"not_a_rule": 0}},
        {"changes": {"settlement_days": []}},
        {"symbol": None},
        {"profile": "sse_main"},
        {"reason": ""},
        {"source": None},
        {"version": " "},
        {"end": "2023-08-24"},
        {"symbol": " A"},
        {"changes": {"price_tick": float("nan")}},
    ],
)
def test_malformed_override_rejected(change):
    with pytest.raises((ValueError, TypeError)):
        override(**change)


@pytest.mark.parametrize(
    "change",
    [
        {"settlement_days": -1},
        {"price_tick": 0},
        {"buy_minimum": 2_000_000},
        {"instrument_kind": "bond"},
    ],
)
def test_invalid_effective_rule_is_rejected(change):
    with pytest.raises(ValueError):
        rules([override(changes=change)])


@pytest.mark.parametrize(
    "item",
    [
        override(symbol="missing"),
        override(symbol=None, profile="missing"),
        override(start="2023-08-23"),
        override(end="2023-08-31"),
    ],
)
def test_unknown_scope_or_outside_coverage_rejected(item):
    with pytest.raises(ValueError):
        rules([item])


def test_gaps_and_same_level_conflicts_fail_but_distinct_fields_can_overlap():
    data = data_for([10, 10, 10])
    period = data.rules.periods[0]
    gap = RuleBook((replace(period, end="2025-01-02"), replace(period, start="2025-01-06")))
    with pytest.raises(ValueError, match="outside covered"):
        gap.with_overrides([override(start="2025-01-02", end="2025-01-06")])
    with pytest.raises(ValueError, match="conflicting overrides"):
        rules([override(), override(start="2023-08-28", changes={"settlement_days": 1})])
    distinct = override(changes={"stamp_duty_sell": 0})
    book = rules([override(), distinct])
    assert book.at("A", date(2023, 8, 28)).rule.stamp_duty_sell == 0
    with pytest.raises(ValueError, match="conflicting overrides"):
        rules([override()]).with_overrides([override()])


def test_same_level_joint_quantity_changes_and_empty_override_are_supported():
    a = override(changes={"buy_minimum": 2_000_000})
    b = override(changes={"order_maximum": 3_000_000})
    assert rules([a, b]).at("A", date(2023, 8, 28)).rule.buy_minimum == 2_000_000
    original = rules()
    assert original.with_overrides([]) is original
    with pytest.raises(ValueError, match="RuleOverride"):
        original.with_overrides([{}])
    with pytest.raises(ValueError, match="sequence"):
        original.with_overrides(None)


def test_rulebook_metadata_is_validated_and_copied():
    periods = data_for([10, 10]).rules.periods
    pairs = [["A", "sse_main"]]
    book = RuleBook(periods, profiles=pairs)
    pairs[0][1] = "sse_star"
    assert book.profiles == (("A", "sse_main"),)
    for fields in [
        {"preset_version": []},
        {"profiles": (("missing", "sse_main"),)},
        {"profiles": (("A", "sse_main"), ("A", "sse_main"))},
        {"profiles": (("A", None),)},
    ]:
        with pytest.raises(ValueError):
            RuleBook(periods, **fields)


def test_preset_coverage_launch_date_and_t0_etf_profiles():
    book = china_rules({"A": "szse_chinext", "S": "sse_star"}, start="2015-09-09", end="2026-10-12")
    assert book.at("A", date(2015, 9, 9)).rule.order_maximum == 1_000_000
    assert book.at("A", date(2026, 10, 12)).rule.order_maximum == 300_000
    assert "20260424" in book.at("S", date(2026, 7, 6)).source
    assert book.at("S", date(2019, 7, 22)).rule.buy_minimum == 200
    with pytest.raises(ValueError, match="missing historical"):
        book.at("S", date(2019, 7, 21))
    with pytest.raises(ValueError, match="no verified dates"):
        china_rules({"S": "sse_star"}, start="2015-09-09", end="2019-07-21")
    for name in (
        "sse_bond_etf",
        "szse_bond_etf",
        "sse_gold_etf",
        "szse_gold_etf",
        "sse_cross_border_t0_etf",
        "szse_cross_border_t0_etf",
    ):
        etf = china_rules({"E": name}, start="2015-09-09", end="2026-10-12")
        rule = etf.at("E", date(2026, 7, 6)).rule
        assert rule.settlement_days == rule.stamp_duty_sell == rule.transfer_fee == 0
        assert rule.instrument_kind == "etf"
        assert float(rule.price_tick) == 0.001
