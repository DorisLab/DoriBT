from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from engine_fixtures import data_for

from doribt import Backtest, Costs, Instrument, MarketData, china_rules


def market(dates, profile="sse_main", kind="stock", prices=None, bounds=None):
    prices = prices or [10] * len(dates)
    bounds = bounds or [(None, None)] * len(dates)
    rows = [
        dict(
            session=session,
            symbol="A",
            status="trading",
            open=price,
            close=price,
            high=price,
            low=price,
            volume=1_000_000,
            upper_limit=upper,
            lower_limit=lower,
        )
        for session, price, (upper, lower) in zip(dates, prices, bounds, strict=True)
    ]
    return MarketData.from_records(
        rows,
        calendar=dates,
        instruments=[Instrument(symbol="A", kind=kind)],
        rules=china_rules({"A": profile}, start=dates[0], end=dates[-1]),
        source="synthetic prices and calendar; sourced historical rule changes",
    )


@pytest.mark.parametrize(
    "session,stamp,transfer,maximum",
    [
        ("2020-01-01", ".001", ".00002", 1_000_000),
        ("2020-08-23", ".001", ".00002", 1_000_000),
        ("2020-08-24", ".001", ".00002", 300_000),
        ("2022-04-28", ".001", ".00002", 300_000),
        ("2022-04-29", ".001", ".00001", 300_000),
        ("2023-08-27", ".001", ".00001", 300_000),
        ("2023-08-28", ".0005", ".00001", 300_000),
        ("2025-12-31", ".0005", ".00001", 300_000),
    ],
)
def test_policy_changes_are_inclusive_and_preserve_source(session, stamp, transfer, maximum):
    rules = china_rules({"A": "szse_chinext"}, start="2020-01-01", end="2025-12-31")
    period = rules.at("A", date.fromisoformat(session))
    assert period.rule.stamp_duty_sell == Decimal(stamp)
    assert period.rule.transfer_fee == Decimal(transfer)
    assert period.rule.order_maximum == maximum
    assert "2020-2025" in period.version
    assert "mof.gov.cn" in period.source
    assert "szse.cn" in period.source
    assert "hkex.com.hk" in period.source


@pytest.mark.parametrize("profile", ["sse_equity_etf", "szse_equity_etf"])
def test_equity_etf_rules_are_explicit_and_have_no_stock_trade_taxes(profile):
    book = china_rules({"arbitrary-name": profile}, start="2020-01-01", end="2025-12-31")
    assert len(book.periods) == 1
    rule = book.periods[0].rule
    assert rule.instrument_kind == "etf"
    assert rule.price_tick == Decimal(".001")
    assert rule.stamp_duty_sell == rule.transfer_fee == 0
    assert rule.settlement_days == 1
    assert rule.buy_minimum == rule.buy_step == rule.sell_step == 100


@pytest.mark.parametrize(
    "dates,fees,final",
    [
        (["2022-04-27", "2022-04-28", "2022-04-29"], [(0, 0.2), (10, 0.1)], 19989.7),
        (["2023-08-24", "2023-08-25", "2023-08-28"], [(0, 0.1), (5, 0.1)], 19994.8),
    ],
)
def test_actual_execution_uses_fill_date_fees(backend, dates, fees, final):
    data = market(dates)

    def round_trip(ctx):
        if ctx.session == data.sessions[0]:
            ctx.order("A", 1000)
        elif ctx.session == data.sessions[1]:
            ctx.order("A", -1000)

    result = Backtest(
        data, initial_cash=20000, costs=Costs(commission=0, minimum_commission=0)
    ).run(round_trip, backend=backend)
    assert [(f.stamp_duty, f.transfer_fee) for f in result.fills] == fees
    assert result.cash[-1] == final
    assert result.equity[-1] == final


def test_explicit_profile_cannot_conflict_with_instrument_kind():
    with pytest.raises(ValueError, match="instrument kind conflicts"):
        market(["2025-01-02"], profile="sse_equity_etf", kind="stock")


@pytest.mark.parametrize(
    "profiles,start,end",
    [
        ({}, "2020-01-01", "2025-12-31"),
        ({"A": "guess-from-code"}, "2020-01-01", "2025-12-31"),
        ({"A": "sse_main"}, "2019-12-31", "2025-12-31"),
        ({"A": "sse_main"}, "2020-01-01", "2026-01-01"),
        ({"A": "sse_main"}, "2025-01-01", "2020-01-01"),
    ],
)
def test_no_silent_profile_or_date_fallback(profiles, start, end):
    with pytest.raises(ValueError):
        china_rules(profiles, start=start, end=end)


def test_custom_rule_can_remain_market_neutral():
    original = data_for([10, 10, 10])
    custom = replace(original, instruments=(Instrument(symbol="A", kind="etf"),))
    assert custom.rules.periods[0].rule.instrument_kind is None


def test_target_sizing_sees_rules_at_the_current_session():
    book = china_rules({"A": "sse_star"}, start="2025-01-02", end="2025-01-03")
    rule = book.periods[0].rule
    assert (rule.buy_minimum, rule.sell_minimum, rule.buy_step, rule.sell_step) == (200, 200, 1, 1)
    with pytest.raises(ValueError, match="missing historical rule"):
        book.at("A", date(2025, 1, 6))
