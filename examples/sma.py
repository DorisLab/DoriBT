"""Run with: uv run python examples/sma.py [--backend numba]. Synthetic data."""

import argparse

import numpy as np

from doribt.experimental import Config, DailyBars, backtest


def sma_regime(close, fast=5, slow=20):
    signal = np.zeros(len(close), dtype=np.int8)
    for i in range(slow, len(close)):
        # Session i sees only completed closes strictly before i.
        signal[i] = close[i - fast : i].mean() > close[i - slow : i].mean()
    return signal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    args = parser.parse_args()
    rng = np.random.default_rng(7301)
    close = np.round(2 * np.exp(np.cumsum(rng.normal(0, 0.01, 240))), 3)
    op = np.round(np.r_[2.0, close[:-1]] * (1 + rng.normal(0, 0.003, 240)), 3)
    dates = np.busday_offset("2025-01-02", np.arange(240))
    bars = DailyBars(
        dates, op, close, np.full(240, 5.0), np.full(240, 0.1), np.zeros(240, dtype=bool)
    )
    config = Config()
    result = backtest(bars, sma_regime(close), config, backend=args.backend)
    print("SYNTHETIC DEMO: prices, calendar and limits are not market data.")
    print(f"Model: {result.model}; backend: {result.backend}")
    print(f"Final equity: {result.equity[-1, 0]:,.2f}; fills: {len(result.fills)}")
    print(f"Total return: {result.total_return(config.initial_cash)[0]:.2%}")


if __name__ == "__main__":
    main()
