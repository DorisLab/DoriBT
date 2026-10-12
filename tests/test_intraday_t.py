from dataclasses import replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pytest
from minute_fixtures import minute_data

from doribt import Backtest, Costs, PositionTargets, Reason, RuleOverride, china_rules
from examples.intraday_t import DAYS, SYMBOL, run_case, sample


@pytest.mark.parametrize("frequency", ["1min", "5min"])
@pytest.mark.parametrize(
    "mode,expected,ending",
    [
        ("t0", [1000, -1000, 1000, -1000], 0),
        ("native", [1000, -1000, 1000, -1000], 0),
        ("t1", [1000], 1000),
        ("inventory", [1000, -1000, 1000], 1000),
    ],
)
def test_minute_do_t_rules_and_independent_cash_ledger(backend, frequency, mode, expected, ending):
    result = run_case(mode, backend, frequency)
    assert [fill.quantity for fill in result.fills] == expected
    assert result.holdings[-1, 0] == ending
    cash, holdings = Decimal(100_000), 0
    by_time = {}
    for fill in result.fills:
        assert fill.quantity < 0 or Decimal(str(fill.price)) == Decimal("10.001")
        assert fill.quantity > 0 or Decimal(str(fill.price)) == Decimal("10.199")
        value = abs(fill.quantity) * Decimal(str(fill.price))
        commission = max(
            Decimal(1), (value * Decimal(".0003")).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
        )
        assert fill.commission_units == int(commission * 10_000)
        assert fill.stamp_duty_units == fill.transfer_fee_units == 0
        by_time.setdefault(fill.timestamp, []).append((fill.quantity, value, commission))
    data = sample(mode, frequency)
    closes = data.prices("close")[:, 0]
    for index, point in enumerate(data.timeline):
        for quantity, value, commission in by_time.get(point, ()):
            cash -= value if quantity > 0 else -value
            cash -= commission
            holdings += quantity
        assert result.cash_units[index] == int(cash * 10_000)
        assert result.holdings[index, 0] == holdings
        equity = cash + holdings * Decimal(str(closes[index]))
        assert result.equity_units[index] == int(equity * 10_000)
    assert result.equity_units[-1] == int((cash + ending * 10) * 10_000)
    assert result.sellable[-1, 0] == 0
    overrides = result.run_info.to_dict()["data"]["rule_provenance"]["overrides"]
    assert len(overrides) == (1 if mode == "t0" else 0)
    if mode in ("t0", "native"):
        assert result.equity_units[-1] == 1_003_838_800
        assert all(fill.session == DAYS[1] for fill in result.fills)
    if mode == "inventory":
        assert result.equity_units[-1] == 1_001_879_400
        assert result.fills[0].session == DAYS[0]
    if mode in ("t1", "inventory"):
        assert any(order.reason == Reason.INSUFFICIENT_SELLABLE for order in result.orders)


def test_day_scoped_t0_uses_trading_days_and_does_not_retroactively_unlock_lots(backend):
    data = minute_data(days=3, volume=100000)
    overrides = [
        RuleOverride(
            symbol="A",
            start="2025-01-03",
            end="2025-01-03",
            changes={"settlement_days": 0},
            reason="仅第二日 T+0",
            source="scenario",
            version="1",
        )
    ]
    book = china_rules(
        {"A": "sse_main"}, start=data.sessions[0], end=data.sessions[-1], overrides=overrides
    )
    data = replace(data, rules=book)

    def strategy(ctx):
        if ctx.bar_index in (0, 242, 480):
            ctx.order("A", 100)
        elif ctx.bar_index in (1, 240, 243, 481):
            ctx.order("A", -100)

    result = Backtest(data, costs=Costs(commission=0, minimum_commission=0)).run(
        strategy, backend=backend
    )
    assert [fill.quantity for fill in result.fills] == [100, -100, 100, -100, 100]
    assert [fill.timestamp for fill in result.fills] == [
        data.timeline[i] for i in (1, 241, 243, 244, 481)
    ]
    assert result.sellable[-1, 0] == 0
    assert book.at("A", date(2025, 1, 6)).rule.settlement_days == 1


def test_same_day_switch_uses_fill_date_and_both_precomputed_paths(backend):
    data = sample("t0", "5min")
    quantities = [0] * len(data.timeline)
    for index in (48, 50):
        quantities[index] = 1000
    target = PositionTargets(sessions=data.timeline, quantities={SYMBOL: quantities})
    fast = Backtest(data, costs=Costs(commission=0, minimum_commission=0)).run(
        target, backend=backend
    )

    def callback(ctx):
        index = ctx.bar_index
        if index == 0 or quantities[index] != quantities[index - 1]:
            ctx.target_positions({SYMBOL: quantities[index]})

    slow = Backtest(data, costs=Costs(commission=0, minimum_commission=0)).run(
        callback, backend=backend
    )
    assert [fill.quantity for fill in fast.fills] == [1000, -1000, 1000, -1000]
    np.testing.assert_array_equal(fast.cash_units, slow.cash_units)
    np.testing.assert_array_equal(fast.sellable, slow.sellable)
    assert fast.fills == slow.fills


def test_stock_t0_override_keeps_commission_and_stock_taxes(backend):
    data = minute_data(days=1, volume=100000)
    item = RuleOverride(
        symbol="A",
        start=data.sessions[0],
        end=data.sessions[0],
        changes={"settlement_days": 0},
        reason="股票 T+0 情景",
        source="scenario",
        version="1",
    )
    data = replace(
        data,
        rules=china_rules(
            {"A": "sse_main"}, start=data.sessions[0], end=data.sessions[0], overrides=[item]
        ),
    )

    def strategy(ctx):
        if ctx.bar_index in (0, 2):
            ctx.order("A", 1000)
        elif ctx.bar_index in (1, 3):
            ctx.order("A", -1000)

    result = Backtest(data, costs=Costs(commission=".0003", minimum_commission=1)).run(
        strategy, backend=backend
    )
    assert [fill.quantity for fill in result.fills] == [1000, -1000, 1000, -1000]
    assert [fill.stamp_duty_units for fill in result.fills] == [0, 50000, 0, 50000]
    assert [fill.transfer_fee_units for fill in result.fills] == [1000] * 4
    assert [fill.commission_units for fill in result.fills] == [30000] * 4
    assert result.cash_units[-1] == 999_776_000
    assert result.holdings[-1, 0] == 0


def test_new_t0_does_not_unlock_older_delayed_lots(backend):
    data = minute_data(days=3, volume=100000)
    items = [
        RuleOverride(
            symbol="A",
            start=session,
            end=session,
            changes={"settlement_days": delay},
            reason="批次可卖日测试",
            source="scenario",
            version="1",
        )
        for session, delay in [(data.sessions[0], 2), (data.sessions[1], 0)]
    ]
    data = replace(
        data,
        rules=china_rules(
            {"A": "sse_main"}, start=data.sessions[0], end=data.sessions[-1], overrides=items
        ),
    )

    def strategy(ctx):
        if ctx.bar_index in (0, 242):
            ctx.order("A", 100)
        elif ctx.bar_index in (240, 243, 480):
            ctx.order("A", -100)

    result = Backtest(data, costs=Costs(commission=0, minimum_commission=0)).run(
        strategy, backend=backend
    )
    assert [fill.quantity for fill in result.fills] == [100, 100, -100, -100]
    assert [fill.timestamp for fill in result.fills] == [
        data.timeline[i] for i in (1, 243, 244, 481)
    ]
    assert result.sellable[241, 0] == 0
    assert result.holdings[244, 0] == 100
    assert result.holdings[-1, 0] == 0
