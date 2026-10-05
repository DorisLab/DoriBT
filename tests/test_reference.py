"""Independent Decimal oracle, with reproducible synthetic data only."""

from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from doribt.experimental import Config, DailyBars, backtest

D = Decimal


def market_reason(suspended, buy, sell, op, hi, lo):
    if suspended:
        return 1
    if buy and op >= hi:
        return 2
    if sell and op <= lo:
        return 3
    return 0


def reference(bars, regime, config):
    n, m = regime.shape
    cash = [D(str(config.initial_cash)) for _ in range(m)]
    shares = [0] * m
    history, trades, reasons = [], [], np.zeros((n, m), dtype=int)
    for i in range(n):
        for j in range(m):
            buy = regime[i, j] == 1 and shares[j] == 0
            sell = regime[i, j] == 0 and shares[j] > 0
            if not buy and not sell:
                continue
            op, hi, lo = (D(str(a[i])) for a in [bars.open, bars.upper_limit, bars.lower_limit])
            reasons[i, j] = market_reason(bars.suspended[i], buy, sell, op, hi, lo)
            if reasons[i, j] == 0:
                slip = D(config.slippage_ticks) / 1000
                px = min(op + slip, hi) if buy else max(op - slip, lo)
                q = shares[j]
                if buy:
                    lots = cash[j] * D(str(config.entry_weight)) / (px * 100)
                    q = int(lots.to_integral_value(rounding=ROUND_FLOOR)) * 100
                while q:
                    fee = max(
                        D(str(config.minimum_commission)),
                        (D(q) * px * D(str(config.commission_rate))).quantize(
                            D("0.01"), rounding=ROUND_HALF_UP
                        ),
                    )
                    if not buy or D(q) * px + fee <= cash[j]:
                        break
                    q -= 100
                if not q or (sell and cash[j] + D(q) * px < fee):
                    reasons[i, j] = 4
                    continue
                signed = q if buy else -q
                cash[j] -= D(signed) * px + fee
                shares[j] += signed
                trades.append((i, j, signed, float(px), float(fee)))
        history.append(
            [
                (float(cash[j]), shares[j], float(cash[j] + D(shares[j]) * D(str(bars.close[i]))))
                for j in range(m)
            ]
        )
    return np.array(history), trades, reasons


def test_seeded_paths_against_independent_decimal(backend):
    rng = np.random.default_rng(7301)
    op = rng.integers(1000, 4000, size=200) / 1000
    close = rng.integers(1000, 4000, size=200) / 1000
    hi, lo = np.full(200, 10.0), np.full(200, 0.1)
    hi[::13] = op[::13]
    lo[::17] = op[::17]
    # Daily close must respect the declared synthetic limits too.
    close = np.clip(close, lo, hi)
    b = DailyBars(
        np.arange(200) + np.datetime64("2020-01-01"), op, close, hi, lo, rng.random(200) < 0.05
    )
    regime = rng.integers(0, 2, size=(200, 7))
    config = Config(initial_cash=100000, entry_weight=1)
    expected, trades, reasons = reference(b, regime, config)
    result = backtest(b, regime, config, backend=backend)
    np.testing.assert_array_equal(result.cash, expected[:, :, 0])
    np.testing.assert_array_equal(result.position, expected[:, :, 1])
    np.testing.assert_array_equal(result.equity, expected[:, :, 2])
    assert result.fills.tolist() == trades
    np.testing.assert_array_equal(result.blocked, reasons)


@settings(max_examples=80, deadline=None, derandomize=True)
@given(
    ticks=st.lists(st.integers(100, 100_000), min_size=1, max_size=20),
    seed=st.integers(0, 2**32 - 1),
    initial=st.integers(1_000, 1_000_000),
    rate=st.integers(0, 10_000),
    minimum=st.integers(0, 1_000),
    weight=st.integers(1, 1_000_000),
)
def test_generated_ledgers_match_decimal(ticks, seed, initial, rate, minimum, weight):
    """Vary fees, affordability, paths, halts and independent accounts, not just JIT."""
    n = len(ticks)
    rng = np.random.default_rng(seed)
    prices = np.array(ticks) / 1000
    b = DailyBars(
        np.arange(n) + np.datetime64("2020-01-01"),
        prices,
        prices.copy(),
        np.full(n, 100.0),
        np.full(n, 0.001),
        rng.random(n) < 0.2,
    )
    regime = rng.integers(0, 2, size=(n, 3))
    config = Config(
        initial_cash=initial / 100,
        entry_weight=weight / 1_000_000,
        commission_rate=rate / 1_000_000,
        minimum_commission=minimum / 100,
    )
    expected, trades, reasons = reference(b, regime, config)
    result = backtest(b, regime, config)
    np.testing.assert_array_equal(result.cash, expected[:, :, 0])
    np.testing.assert_array_equal(result.position, expected[:, :, 1])
    np.testing.assert_array_equal(result.equity, expected[:, :, 2])
    np.testing.assert_array_equal(result.blocked, reasons)
    assert result.fills.tolist() == trades
    assert np.all(result.cash >= 0) and np.all(result.position >= 0)
