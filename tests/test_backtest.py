from dataclasses import replace

import numpy as np
import pytest

from doribt.experimental import BlockReason, Config, DailyBars, backtest


def bars(prices):
    p = np.array(prices, dtype=float)
    return DailyBars(
        np.arange(len(p)) + np.datetime64("2020-01-01"),
        p,
        p.copy(),
        np.full(len(p), 100.0),
        np.full(len(p), 0.001),
        np.zeros(len(p), dtype=bool),
    )


@pytest.fixture(params=["python", "numba"])
def backend(request):
    return request.param


def reconcile(b, result, initial_cash):
    flow = np.zeros_like(result.cash)
    shares = np.zeros_like(result.position)
    for fill in result.fills:
        day, account, quantity, price, fee = fill
        assert quantity != 0 and quantity % 100 == 0
        assert not b.suspended[day]
        flow[day, account] -= quantity * price + fee
        shares[day, account] += quantity
    np.testing.assert_allclose(result.cash, initial_cash + flow.cumsum(axis=0), atol=1e-7, rtol=0)
    np.testing.assert_array_equal(result.position, shares.cumsum(axis=0))
    np.testing.assert_allclose(result.equity, result.cash + result.position * b.close[:, None])
    assert (result.cash >= 0).all() and (result.position >= 0).all()


def test_manual_open_close_lot_and_minimum_fee(backend):
    b = bars([10, 11])
    b.close[0] = 10.5
    r = backtest(b, [1, 0], Config(initial_cash=10000, slippage_ticks=0), backend=backend)
    np.testing.assert_array_equal(r.position[:, 0], [900, 0])
    np.testing.assert_array_equal(r.cash[:, 0], [995, 10890])
    np.testing.assert_array_equal(r.equity[:, 0], [10445, 10890])
    np.testing.assert_array_equal(r.fills["commission"], [5, 5])
    reconcile(b, r, 10000)


def test_fee_affordability_and_half_cent_regression(backend):
    r = backtest(bars([10, 10]), [1, 0], Config(entry_weight=1, slippage_ticks=0), backend=backend)
    np.testing.assert_array_equal(r.position[:, 0], [9900, 0])
    np.testing.assert_array_equal(r.fills["commission"], [29.70, 29.70])
    np.testing.assert_array_equal(r.cash[:, 0], [970.30, 99940.60])
    r = backtest(bars([2.780]), [1], Config(initial_cash=110000, slippage_ticks=0), backend=backend)
    assert r.fills[0]["quantity"] == 37500
    assert r.fills[0]["commission"] == 31.28  # 37500 * 2.780 * .0003 = 31.275


def test_suspend_and_limit_retry(backend):
    b = bars([10, 10, 9, 9])
    b.suspended[0] = True
    b.lower_limit[2] = 9
    r = backtest(b, [1, 1, 0, 0], Config(initial_cash=10000, slippage_ticks=0), backend=backend)
    np.testing.assert_array_equal(r.blocked[:, 0], [1, 0, 3, 0])
    np.testing.assert_array_equal(r.position[:, 0], [0, 900, 900, 0])
    np.testing.assert_array_equal(r.fills["session_index"], [1, 3])
    reconcile(b, r, 10000)


def test_directional_limit_and_replacement(backend):
    b = bars([10, 10, 10, 11])
    b.upper_limit[0] = 10
    b.lower_limit[2] = 10
    b.upper_limit[3] = 11
    r = backtest(b, [1, 0, 1, 0], Config(initial_cash=10000, slippage_ticks=0), backend=backend)
    np.testing.assert_array_equal(r.blocked[:, 0], [2, 0, 0, 0])
    np.testing.assert_array_equal(r.position[:, 0], [0, 0, 900, 0])
    reconcile(b, r, 10000)


def test_slippage_accounts_and_no_final_liquidation(backend):
    b = bars([10, 10])
    r = backtest(b, [[1, 0], [0, 1]], Config(initial_cash=10000), backend=backend)
    np.testing.assert_array_equal(r.fills["price"], [10.001, 9.999, 10.001])
    np.testing.assert_array_equal(r.cash[0], [994.10, 10000])
    np.testing.assert_array_equal(r.position[-1], [0, 900])
    assert r.backend == backend and r.model == "etf-next-open-budget-v0"
    reconcile(b, r, 10000)


def test_zero_size_does_not_charge_commission(backend):
    r = backtest(bars([10]), [1], Config(initial_cash=1000, entry_weight=1), backend=backend)
    assert len(r.fills) == 0
    assert r.blocked[0, 0] == BlockReason.INSUFFICIENT_CASH
    assert r.cash[0, 0] == 1000


def test_extreme_commission_and_numeric_bounds_fail_safely(backend):
    r = backtest(
        bars([1, 1]), [1, 0], Config(initial_cash=1000, commission_rate=1), backend=backend
    )
    assert r.cash.min() >= 0
    b = bars([0.001, 1_000_000])
    b.upper_limit[:] = 1_000_000
    with pytest.raises(ValueError, match="bounds"):
        backtest(b, [1, 1], Config(initial_cash=10_000_000_000, slippage_ticks=0), backend=backend)


@pytest.mark.parametrize(
    "field,value",
    [
        ("initial_cash", float("nan")),
        ("entry_weight", float("inf")),
        ("commission_rate", -0.01),
        ("minimum_commission", 0.001),
        ("slippage_ticks", 0.5),
        ("entry_weight", 1.1),
    ],
)
def test_bad_config(field, value):
    with pytest.raises(ValueError):
        backtest(bars([10]), [0], replace(Config(), **{field: value}))


@pytest.mark.parametrize(
    "kind", ["missing", "off_tick", "order", "empty", "regime", "flags", "limits"]
)
def test_bad_market_input(kind):
    b, regime = bars([10, 10]), [1, 0]
    if kind == "missing":
        b.close[0] = np.nan
    elif kind == "off_tick":
        b.open[0] = 10.0001
    elif kind == "order":
        b.sessions[1] = b.sessions[0]
    elif kind == "empty":
        b, regime = bars([]), []
    elif kind == "regime":
        regime = [1, np.nan]
    elif kind == "flags":
        b = replace(b, suspended=np.array([0, 1]))
    else:
        b.upper_limit[0] = 9
    with pytest.raises(ValueError):
        backtest(b, regime)


def test_unknown_backend_fails():
    with pytest.raises(ValueError, match="backend"):
        backtest(bars([10]), [1], backend="auto")
