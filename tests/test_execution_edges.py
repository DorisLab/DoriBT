from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pytest
from engine_fixtures import data_for

from doribt import Backtest, Costs, WeightTargets
from doribt.execution import fee
from doribt.orders import Reason


def test_fee_ties_and_large_notional_stay_exact():
    for value in (104_250_000, 100_000_000_000_000, 16_666_667):
        for rate in (3000, 999999, 1000000):
            expected = (Decimal(value) / 10000 * Decimal(rate) / 1000000).quantize(
                Decimal(".01"), ROUND_HALF_UP
            )
            assert fee(value, rate) == int(expected * 10000)


def test_two_hundred_minimum_one_share_step_is_not_a_hundred_share_lot(backend):
    data = data_for([10] * 3, rule_changes={"buy_minimum": 200, "buy_step": 1, "sell_step": 1})

    def strategy(ctx):
        ctx.order("A", 201 if ctx.session == data.sessions[0] else -201)

    result = Backtest(data, costs=Costs(commission=0, minimum_commission=0)).run(
        strategy, backend=backend
    )
    assert [fill.quantity for fill in result.fills] == [201, -201]


def test_sell_at_lower_limit_expires_and_slippage_checks_known_boundaries(backend):
    data = data_for([10] * 3, changes={2: {"upper_limit": 11, "lower_limit": 10}})

    def strategy(ctx):
        ctx.order("A", 100 if ctx.session == data.sessions[0] else -100)

    result = Backtest(data).run(strategy, backend=backend)
    assert result.orders[1].reason == Reason.SELL_AT_LOWER_LIMIT
    data = data_for([10] * 3, changes={1: {"upper_limit": 10.01, "lower_limit": 9}})
    result = Backtest(data, costs=Costs(slippage_ticks=2)).run(strategy, backend=backend)
    assert result.orders[0].reason == Reason.PRICE_OUT_OF_RANGE


def test_delisted_holdings_cannot_be_silently_written_off(backend):
    data = data_for(
        [10] * 3,
        changes={2: dict(status="delisted", open=None, high=None, low=None, close=None, volume=0)},
    )
    targets = WeightTargets(sessions=data.sessions, weights={"A": [1, 1, 1]})
    with pytest.raises(ValueError, match="unsupported delisting"):
        Backtest(data).run(targets, backend=backend)


def test_order_and_valuation_overflow_fail_explicitly(backend):
    data = data_for([1_000_000] * 3)

    def strategy(ctx):
        ctx.order("A", 1_000_000_000)

    with pytest.raises(OverflowError, match="notional"):
        Backtest(data).run(strategy, backend=backend)
    data = data_for([1, 1, 1_000_000])
    targets = WeightTargets(sessions=data.sessions, weights={"A": [1, 1, 1]})
    with pytest.raises(OverflowError, match="equity"):
        Backtest(data, initial_cash=100000, costs=Costs(commission=0, minimum_commission=0)).run(
            targets, backend=backend
        )


def test_rebalance_is_explicit_and_strategy_errors_keep_date(backend):
    data = data_for([10, 10, 20, 20])
    targets = WeightTargets(sessions=data.sessions, weights={"A": [0.5] * 4})
    backtest = Backtest(data, initial_cash=10000, costs=Costs(commission=0, minimum_commission=0))
    keep = backtest.run(targets, backend=backend)
    rebalance = backtest.run(replace(targets, rebalance=True), backend=backend)
    assert keep.holdings[-1, 0] == 500
    assert rebalance.holdings[-1, 0] == 400

    def bad_strategy(ctx):
        ctx.order("unknown", 100)

    with pytest.raises(RuntimeError, match="strategy failed at close on 2025-01-02: unknown"):
        backtest.run(bad_strategy, backend=backend)


@pytest.mark.parametrize(
    "weights",
    [{"A": [1, 1]}, {"A": [1.1] * 3}, {"A": [float("nan")] * 3}, {"A": [0.6] * 3, "B": [0.5] * 3}],
)
def test_invalid_targets_rejected(weights):
    with pytest.raises(ValueError):
        WeightTargets(sessions=data_for([10] * 3).sessions, weights=weights)


def test_backend_and_account_validation():
    data = data_for([10] * 3)
    with pytest.raises(ValueError, match="positive"):
        Backtest(data, initial_cash=0)
    with pytest.raises(ValueError, match="whole cents"):
        Costs(minimum_commission=0.001)
    with pytest.raises(ValueError, match="backend"):
        Backtest(data).run(lambda ctx: None, backend="magic")
    result = Backtest(data).run(lambda ctx: None)
    assert result.max_drawdown == 0
    assert result.stats()["fill_count"] == 0
    np.testing.assert_array_equal(result.equity, [100000] * 3)
