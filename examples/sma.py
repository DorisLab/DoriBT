"""Run with: uv run python examples/sma.py [--backend numba]. Synthetic data."""

import argparse

import numpy as np
from numpy.typing import ArrayLike

from doribt.experimental import Backtest, CloseSignals, DailyBars
from doribt.experimental.typing import BoolArray


def sma_hold(close: ArrayLike, fast: int = 5, slow: int = 20) -> BoolArray:
    """Desired holding at each close; Backtest handles next-session execution."""
    if not 0 < fast < slow:
        raise ValueError("moving-average windows require 0 < fast < slow")
    prices = np.asarray(close, dtype=np.float64)
    hold = np.zeros(len(prices), dtype=bool)
    for end in range(slow, len(prices) + 1):
        hold[end - 1] = prices[end - fast : end].mean() > prices[end - slow : end].mean()
    return hold


def synthetic_bars() -> DailyBars:
    """Artificial prices, weekday calendar and limits; not tradable market data."""
    rng = np.random.default_rng(7301)
    close = np.round(2 * np.exp(np.cumsum(rng.normal(0, 0.01, 240))), 3)
    op = np.round(np.r_[2.0, close[:-1]] * (1 + rng.normal(0, 0.003, 240)), 3)
    return DailyBars(
        sessions=np.busday_offset(np.datetime64("2025-01-02"), np.arange(240)),
        open=op,
        close=close,
        upper_limit=np.full(240, 5.0),
        lower_limit=np.full(240, 0.1),
        suspended=np.zeros(240, dtype=bool),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    args = parser.parse_args()
    bars = synthetic_bars()
    signals = CloseSignals(sessions=bars.sessions, hold=sma_hold(bars.close))
    result = Backtest(bars, initial_cash=100_000).run(signals, backend=args.backend)
    print("SYNTHETIC DEMO: prices, calendar and limits are not market data.")
    print(f"Model: {result.model}; backend: {result.backend}")
    print(f"Final equity: {result.equity[-1]:,.2f}; fills: {len(result.fills)}")
    print(f"Total return: {result.total_return:.2%}")
    print(f"Max drawdown: {result.max_drawdown:.2%}")


if __name__ == "__main__":
    main()
