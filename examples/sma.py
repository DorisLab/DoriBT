"""合成均线示例：uv run python examples/sma.py [--backend numba]。"""

import argparse

import numpy as np
from numpy.typing import ArrayLike, NDArray

from doribt import Backtest, Instrument, MarketData, WeightTargets, china_rules


def sma_hold(close: ArrayLike, fast: int = 5, slow: int = 20) -> NDArray[np.bool_]:
    """每次收盘后的目标持仓，由 Backtest 处理下一交易日执行。"""
    if not 0 < fast < slow:
        raise ValueError("moving-average windows require 0 < fast < slow")
    prices = np.asarray(close, dtype=np.float64)
    hold = np.zeros(len(prices), dtype=bool)
    for end in range(slow, len(prices) + 1):
        hold[end - 1] = prices[end - fast : end].mean() > prices[end - slow : end].mean()
    return hold


def synthetic_bars() -> MarketData:
    """人工价格、工作日日历与价格限制，不是真实可交易行情。"""
    rng = np.random.default_rng(7301)
    close = np.round(2 * np.exp(np.cumsum(rng.normal(0, 0.01, 240))), 3)
    op = np.round(np.r_[2.0, close[:-1]] * (1 + rng.normal(0, 0.003, 240)), 3)
    sessions = [str(day) for day in np.busday_offset(np.datetime64("2025-01-02"), np.arange(240))]
    return MarketData.from_records(
        [
            dict(
                session=day,
                symbol="DEMO",
                status="trading",
                open=float(o),
                close=float(c),
                high=float(max(o, c)),
                low=float(min(o, c)),
                volume=1_000_000,
                upper_limit=5,
                lower_limit=0.1,
            )
            for day, o, c in zip(sessions, op, close, strict=True)
        ],
        calendar=sessions,
        instruments=[Instrument(symbol="DEMO", kind="etf")],
        rules=china_rules({"DEMO": "szse_equity_etf"}, start=sessions[0], end=sessions[-1]),
        source="synthetic weekday demo; not an exchange calendar",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    args = parser.parse_args()
    bars = synthetic_bars()
    signals = WeightTargets(
        sessions=bars.sessions, weights={"DEMO": sma_hold(bars.prices("close")[:, 0]) * 0.95}
    )
    result = Backtest(bars, initial_cash=100_000).run(signals, backend=args.backend)
    print("合成示例：价格、日历与价格限制均不是真实行情。")
    print(f"执行后端：{result.backend}")
    print(f"期末权益：{result.equity[-1]:,.2f}；成交数：{len(result.fills)}")
    print(f"总收益率：{result.total_return:.2%}")
    print(f"最大回撤：{result.max_drawdown:.2%}")


if __name__ == "__main__":
    main()
