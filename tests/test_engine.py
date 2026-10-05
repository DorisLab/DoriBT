from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pytest
from engine_fixtures import data_for

from doribt import Backtest, Costs, WeightTargets
from doribt.orders import Reason

FREE = Costs(commission=0, minimum_commission=0)


def test_fixed_shares_use_previous_close_not_execution_price(backend):
    data = data_for([10, 12, 13])
    result = Backtest(data, initial_cash=10_000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [0.5, 0.5, 0.5]}), backend=backend
    )
    assert [order.quantity for order in result.orders] == [500]
    assert [fill.quantity for fill in result.fills] == [500]
    np.testing.assert_array_equal(result.cash, [10000, 4000, 4000])
    np.testing.assert_array_equal(result.equity, [10000, 10000, 10500])
    np.testing.assert_array_equal(result.sellable[:, 0], [0, 0, 500])


def test_shared_cash_sells_before_buys_even_when_symbol_order_opposes(backend):
    data = data_for([10, 10, 20, 20], [10, 10, 11, 11])
    targets = WeightTargets(sessions=data.sessions, weights={"A": [0, 1, 1, 1], "B": [1, 0, 0, 0]})
    result = Backtest(data, initial_cash=10000, costs=FREE).run(targets, backend=backend)
    orders = result.orders
    assert [(o.symbol, o.quantity, o.filled) for o in orders[:3]] == [
        ("B", 1000, 1000),
        ("B", -1000, -1000),
        ("A", 1000, 500),
    ]
    assert orders[2].reason == Reason.INSUFFICIENT_CASH
    assert orders[2].events == ("created", "accepted", "partially_filled", "expired")
    assert result.cash[-1] == 1000
    assert result.holdings[-1].tolist() == [500, 0]
    assert result.equity[-1] == 11000
    assert result.intents[2].status == "unexecuted"  # A still targets the original 1000 shares.


def test_callbacks_cannot_see_future_and_targets_match_precomputed(backend):
    data = data_for([10, 10, 11, 12])
    seen, contexts = [], []

    def strategy(ctx):
        history = ctx.history("A")
        seen.append(history.tolist())
        contexts.append(ctx)
        assert not history.flags.writeable
        ctx.target_weights({"A": 0.5})

    run = Backtest(data, initial_cash=10000, costs=FREE)
    event = run.run(strategy, backend=backend)
    calculated = run.run(
        WeightTargets(sessions=data.sessions, weights={"A": [0.5] * 4}), backend=backend
    )
    assert seen == [[10], [10, 10], [10, 10, 11], [10, 10, 11, 12]]
    np.testing.assert_array_equal(event.equity_units, calculated.equity_units)
    assert event.orders == calculated.orders
    with pytest.raises(RuntimeError, match="during their close callback"):
        contexts[0].order("A", 100)
    with pytest.raises(TypeError):
        contexts[0].account.positions["A"] = None


def test_t_plus_two_retries_target_by_trading_session(backend):
    data = data_for([10] * 5, settlement=2)
    result = Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [1, 0, 0, 0, 0]}), backend=backend
    )
    assert [(str(o.session), o.filled, o.reason) for o in result.orders] == [
        ("2025-01-03", 1000, Reason.NONE),
        ("2025-01-06", 0, Reason.INSUFFICIENT_SELLABLE),
        ("2025-01-07", -1000, Reason.NONE),
    ]
    assert result.cash[-1] == 10000


def test_target_replaced_and_explicit_cancel_remain_in_history(backend):
    data = data_for([10] * 4, changes={1: {"status": "suspended", "volume": 0}})

    def strategy(ctx):
        if ctx.session == data.sessions[0]:
            ctx.target_positions({"A": 100})
        elif ctx.session == data.sessions[1]:
            pending = ctx.target_positions({"A": 200})[0]
            ctx.cancel(pending)

    result = Backtest(data, costs=FREE).run(strategy, backend=backend)
    assert result.orders[0].reason == Reason.SUSPENDED
    assert [intent.reason for intent in result.intents] == ["target_replaced", "user_cancelled"]
    assert not result.fills


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"upper_limit": 10, "lower_limit": 9}, Reason.BUY_AT_UPPER_LIMIT),
        ({"volume": 0}, Reason.NO_VOLUME),
    ],
)
def test_one_session_orders_expire_without_silent_retry(backend, change, reason):
    data = data_for([10] * 4, changes={1: change})

    def strategy(ctx):
        if ctx.session == data.sessions[0]:
            ctx.order("A", 100)

    result = Backtest(data, costs=FREE).run(strategy, backend=backend)
    assert len(result.orders) == 1
    assert result.orders[0].reason == reason
    assert result.intents[0].status == "expired"


def test_invalid_quantity_rejected_and_last_close_not_executed(backend):
    data = data_for([10] * 3)

    def strategy(ctx):
        ctx.order("A", 50)

    result = Backtest(data, costs=FREE).run(strategy, backend=backend)
    assert len(result.orders) == 2
    assert all(o.events == ("created", "rejected") for o in result.orders)
    assert result.intents[-1].reason == "end_of_data"


def test_cent_fees_and_trade_replay_use_independent_decimal(backend):
    data = data_for(
        [10, 10.25, 11.15], rule_changes={"stamp_duty_sell": ".0005", "transfer_fee": ".00001"}
    )

    def strategy(ctx):
        if ctx.session == data.sessions[0]:
            ctx.order("A", 300)
        elif ctx.session == data.sessions[1]:
            ctx.order("A", -300)

    result = Backtest(data, initial_cash=10000).run(strategy, backend=backend)
    cash = Decimal("10000")
    for order, price, direction in zip(result.fills, ("10.25", "11.15"), (1, -1), strict=True):
        value = Decimal(price) * 300
        commission = max(
            Decimal(5), (value * Decimal(".0003")).quantize(Decimal(".01"), ROUND_HALF_UP)
        )
        stamp = (
            Decimal(0)
            if direction == 1
            else (value * Decimal(".0005")).quantize(Decimal(".01"), ROUND_HALF_UP)
        )
        transfer = (value * Decimal(".00001")).quantize(Decimal(".01"), ROUND_HALF_UP)
        cash -= direction * value + commission + stamp + transfer
        assert order.commission_units == int(commission * 10000)
        assert order.stamp_duty_units == int(stamp * 10000)
        assert order.transfer_fee_units == int(transfer * 10000)
    assert result.cash_units[-1] == int(cash * 10000)


def test_future_prices_do_not_change_past_decisions(backend):
    first = data_for([10, 11, 12, 13, 14])
    second = data_for([10, 11, 12, 20, 30])

    def strategy(ctx):
        closes = ctx.history("A", bars=2)
        ctx.target_weights({"A": 0.5 if closes[-1] >= closes.mean() else 0})

    a = Backtest(first, costs=FREE).run(strategy, backend=backend)
    b = Backtest(second, costs=FREE).run(strategy, backend=backend)
    np.testing.assert_array_equal(a.equity_units[:3], b.equity_units[:3])
    assert a.orders == b.orders


def test_repeat_runs_are_independent_and_do_not_mutate_target_input(backend):
    data = data_for([10] * 3)
    weights = [1, 0, 0]
    signals = WeightTargets(sessions=data.sessions, weights={"A": weights})
    weights[:] = [0, 0, 0]
    run = Backtest(data, initial_cash=10000, costs=FREE)
    a, b = run.run(signals, backend=backend), run.run(signals, backend=backend)
    assert len(a.fills) == 2
    np.testing.assert_array_equal(a.cash_units, b.cash_units)
    with pytest.raises(ValueError, match="exactly match"):
        run.run(replace(signals, sessions=["2025-01-01", *data.sessions[1:]]))
