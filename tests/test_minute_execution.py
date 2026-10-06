from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pytest
from minute_fixtures import minute_data

from doribt import Backtest, BarExecution, Costs, FixedBps, FixedTicks, VolumeImpact, WeightTargets

FREE = Costs(commission=0, minimum_commission=0)


def test_partial_fills_keep_order_identity_and_cumulative_minimum(backend):
    data = minute_data(volume=3000)
    result = Backtest(data, execution=BarExecution(participation=0.1)).run(
        lambda ctx: ctx.order("A", 1000, valid_for="day") if ctx.bar_index == 0 else None,
        backend=backend,
    )
    assert [f.quantity for f in result.fills] == [300, 300, 300, 100]
    assert {f.order_id for f in result.fills} == {1}
    assert [f.commission for f in result.fills] == [5, 0, 0, 0]
    assert [f.timestamp for f in result.fills] == list(data.timeline[1:5])
    assert result.orders[0].status == "filled"
    assert result.cash[-1] == 89995
    assert result.orders[0].notional_units == 100_000_000


def test_cumulative_fee_crosses_minimum_and_decimal_replays_every_bar(backend):
    data = minute_data(volume=11000)
    result = Backtest(data, execution=BarExecution(participation=0.1, slippage=FixedBps(5))).run(
        lambda ctx: ctx.order("A", 8000, valid_for="day") if ctx.bar_index == 0 else None,
        backend=backend,
    )
    cash, position, notional, paid = Decimal(100000), 0, Decimal(0), Decimal(0)
    grouped = {}
    for fill in result.fills:
        grouped.setdefault(fill.timestamp, []).append(fill)
    for index, point in enumerate(data.timeline):
        for fill in grouped.get(point, []):
            value = Decimal(fill.quantity) * Decimal("10.01")
            notional += value
            commission = max(
                Decimal(5),
                (notional * Decimal(".0003")).quantize(Decimal(".01"), rounding=ROUND_HALF_UP),
            )
            assert fill.commission_units == int((commission - paid) * 10000)
            cash -= value + commission - paid
            paid = commission
            position += fill.quantity
        assert result.cash_units[index] == int(cash * 10000)
        assert result.holdings[index, 0] == position
        assert result.equity_units[index] == int((cash + position * 10) * 10000)


def test_orders_share_capacity_and_partial_fills_need_not_be_board_lots(backend):
    data = minute_data(volume=670)

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 100, valid_for="day")
            ctx.order("A", 100, valid_for="day")

    result = Backtest(data, costs=FREE, execution=BarExecution(participation=0.1)).run(
        strategy, backend=backend
    )
    assert [f.quantity for f in result.fills] == [67, 33, 34, 66]
    assert [f.order_id for f in result.fills] == [1, 1, 2, 2]
    assert all(
        sum(abs(f.quantity) for f in result.fills if f.timestamp == point) <= 67
        for point in data.timeline
    )


def test_t_plus_one_unlocks_next_trading_day_not_next_minute(backend):
    data = minute_data(volume=100000)

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 100)
        if ctx.bar_index in (1, 239):
            ctx.order("A", -100, valid_for="day")

    result = Backtest(data, costs=FREE).run(strategy, backend=backend)
    assert [f.quantity for f in result.fills] == [100, -100]
    assert result.fills[-1].timestamp == data.timeline[240]
    assert np.all(result.sellable[:240] == 0)
    assert result.orders[1].filled == 0 and result.orders[1].status == "expired"


def test_lunch_does_not_expire_day_order_and_last_bar_order_waits(backend):
    data = minute_data(volume=1000)

    def strategy(ctx):
        if ctx.bar_index in (118, 239):
            ctx.order("A", 100, valid_for="day")

    result = Backtest(data, costs=FREE).run(strategy, backend=backend)
    assert [f.timestamp for f in result.fills] == [data.timeline[i] for i in (119, 120, 240, 241)]
    assert result.fills[1].timestamp.hour == 13


def test_cancel_releases_cash_and_does_not_erase_partial_fills(backend):
    seen = []

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 1000, valid_for="day")
        elif ctx.bar_index == 1:
            seen.append(ctx.account.frozen_cash)
            ctx.cancel_order(1)
            ctx.order("A", 100, valid_for="day")

    result = Backtest(minute_data(), initial_cash=10000, costs=FREE).run(strategy, backend=backend)
    assert seen == [9500]
    assert [o.status for o in result.orders] == ["cancelled", "filled"]
    assert result.orders[0].filled == 50
    assert result.holdings[-1, 0] == 150


@pytest.mark.parametrize(
    "slippage,price", [(FixedTicks(2), 10.02), (FixedBps(5), 10.01), (VolumeImpact(0.1), 10.01)]
)
def test_slippage_models_adverse_tick_rounding(backend, slippage, price):
    result = Backtest(
        minute_data(volume=1000),
        costs=FREE,
        execution=BarExecution(participation=0.1, slippage=slippage),
    ).run(lambda ctx: ctx.order("A", 100) if ctx.bar_index == 0 else None, backend=backend)
    assert result.fills[0].price == price


@pytest.mark.parametrize(
    "change,limit,reason",
    [
        ({"high": 10}, None, "price_out_of_range"),
        ({}, 10, "limit_price"),
        ({"upper_limit": 10, "high": 10}, None, "buy_at_upper_limit"),
        ({"phase": "auction"}, None, "auction"),
    ],
)
def test_price_and_phase_rejections_never_clamp(backend, change, limit, reason):
    data = minute_data(changes={1: change})
    result = Backtest(data, execution=BarExecution(slippage=FixedTicks(1))).run(
        lambda ctx: ctx.order("A", 100, limit_price=limit) if ctx.bar_index == 0 else None,
        backend=backend,
    )
    assert not result.fills
    assert result.orders[0].reason == reason


def test_cash_reservation_prevents_overcommit_and_order_retains_remainder(backend):
    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 1000, valid_for="day")
            ctx.order("A", 1000, valid_for="day")

    result = Backtest(minute_data(volume=10000), initial_cash=10000).run(strategy, backend=backend)
    assert result.holdings[-1, 0] == 999
    assert result.cash[-1] == 5
    assert result.orders[0].remaining == 1
    assert result.orders[0].reason == "insufficient_cash"
    assert result.orders[1].filled == 0
    assert sum(f.commission for f in result.fills) == 5


def test_target_survives_day_expiry_and_replacement_cancels_old_child(backend):
    data = minute_data(volume=10)

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.target_positions({"A": 1000})
        if ctx.bar_index == 250:
            ctx.target_positions({"A": 100})

    result = Backtest(data, costs=FREE, execution=BarExecution(participation=1)).run(
        strategy, backend=backend
    )
    assert result.intents[0].status == "fulfilled"
    assert result.holdings[-1, 0] == 100


def test_minute_weight_targets_and_callback_are_identical(backend):
    data = minute_data()
    test = Backtest(data, costs=FREE)
    first = test.run(lambda ctx: ctx.target_weights({"A": 0.1}), backend=backend)
    second = test.run(
        WeightTargets(sessions=data.timeline, weights={"A": [0.1] * len(data.timeline)}),
        backend=backend,
    )
    assert first.fills == second.fills
    np.testing.assert_array_equal(first.equity_units, second.equity_units)


def test_future_bars_do_not_change_callback_history_or_past_results():
    data = minute_data()
    seen = []

    def strategy(ctx):
        if ctx.bar_index < 3:
            seen.append((ctx.now, ctx.history("A").tolist()))
        if ctx.bar_index == 0:
            ctx.order("A", 1000, valid_for="day")

    first = Backtest(data).run(strategy)
    original = seen[:]
    seen.clear()
    bars = tuple(
        replace(bar, open=110000, close=110000) if i > 10 else bar
        for i, bar in enumerate(data.bars)
    )
    changed = Backtest(replace(data, bars=bars)).run(strategy)
    assert seen == original
    np.testing.assert_array_equal(first.equity_units[:11], changed.equity_units[:11])


def test_legacy_slippage_conflict_and_invalid_orders_are_explicit():
    with pytest.raises(ValueError, match="BarExecution.slippage"):
        Backtest(minute_data(), costs=Costs(slippage_ticks=1))
    result = Backtest(minute_data()).run(
        lambda ctx: ctx.order("A", 13) if ctx.bar_index == 0 else None
    )
    assert result.orders[0].status == "rejected"
    assert not result.fills
