"""使用公开 API，在同一份人工双证券行情上运行三种策略。"""

import argparse
from datetime import date, timedelta

import numpy as np

from doribt import (
    Backtest,
    Context,
    Instrument,
    MarketData,
    RuleBook,
    RulePeriod,
    RunConfig,
    TradingRule,
)


def synthetic_market() -> MarketData:
    dates = [date(2025, 1, 2) + timedelta(days=i) for i in range(120)]
    sessions = [item for item in dates if item.weekday() < 5]
    count = len(sessions)
    index = np.arange(count)
    paths = {
        "ALPHA": np.round(10 + index * 0.015 + np.sin(index / 4), 2),
        "BETA": np.round(12 - index * 0.005 + np.cos(index / 5), 2),
    }
    # 人工日历与规则，不代表真实交易所节假日或制度覆盖情况。
    rule = TradingRule(
        price_tick=".01",
        buy_minimum=100,
        buy_step=100,
        sell_step=100,
        settlement_days=1,
        stamp_duty_sell=0,
        transfer_fee=0,
    )
    rules = RuleBook(
        tuple(
            RulePeriod(
                symbol=symbol,
                start=sessions[0],
                end=sessions[-1],
                rule=rule,
                source="人工 ETF 规则",
                version="1",
            )
            for symbol in paths
        )
    )
    rows = [
        dict(
            session=session,
            symbol=symbol,
            status="trading",
            open=str(values[i]),
            high=str(values[i]),
            low=str(values[i]),
            close=str(values[i]),
            volume=1_000_000,
            upper_limit=None,
            lower_limit=None,
        )
        for i, session in enumerate(sessions)
        for symbol, values in paths.items()
    ]
    return MarketData.from_records(
        rows,
        calendar=sessions,
        instruments=[Instrument(symbol=symbol, kind="etf") for symbol in paths],
        rules=rules,
        source="固定人工双证券行情",
    )


def buy_and_hold(ctx: Context) -> None:
    ctx.target_weights({"ALPHA": 0.95})


def moving_average(ctx: Context) -> None:
    closes = ctx.history("ALPHA", bars=20)
    if len(closes) < 20:
        return
    weight = 0.95 if closes[-5:].mean() > closes.mean() else 0
    ctx.target_weights({"ALPHA": weight})


def rotation(ctx: Context) -> None:
    # 每隔五个已完成交易日决策一次，不代表自然周的周末。
    count = ctx.bar_index + 1
    if count < 20 or count % 5:
        return
    momentum = {}
    for symbol in ctx.symbols:
        history = ctx.history(symbol, bars=20)
        momentum[symbol] = float(history[-1] / history[0] - 1)
    winner = max(momentum, key=lambda symbol: momentum[symbol])
    ctx.target_weights({winner: 0.95}, rebalance=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    args = parser.parse_args()
    data = synthetic_market()
    print("合成示例：日期、价格与规则均为人工构造。")
    for strategy in (buy_and_hold, moving_average, rotation):
        config = RunConfig(initial_cash=100_000, backend=args.backend)
        result = Backtest(data, config=config).run(strategy)
        print(strategy.__name__, result.report().stats)


if __name__ == "__main__":
    main()
