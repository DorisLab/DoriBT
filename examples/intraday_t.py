"""人工分钟行情：比较 T+0 情景、T+1 与利用昨日底仓做 T。"""

import argparse
from datetime import date
from typing import Literal

from doribt import (
    Backtest,
    BacktestResult,
    BarExecution,
    Context,
    Costs,
    FixedTicks,
    Instrument,
    MarketData,
    MinuteClock,
    RuleOverride,
    RunConfig,
    china_rules,
)

DAYS = (date(2025, 1, 2), date(2025, 1, 3))
SYMBOL = "DEMO"
MODES = ("t0", "t1", "inventory", "native")


def sample(mode: str, frequency: str = "1min") -> MarketData:
    """生成完整人工网格；只有第二日第一批 bar 存在演示信号。"""
    if mode not in MODES:
        raise ValueError("unknown intraday scenario")
    clock = MinuteClock.build(DAYS, frequency)
    per_day = len(clock.timestamps) // len(DAYS)
    closes = (10.2, 9.9, 10.2, 9.9) if mode == "inventory" else (9.9, 10.2, 9.9, 10.2)
    opens = (10, 10.2, 10, 10.2, 10) if mode == "inventory" else (10, 10, 10.2, 10, 10.2)
    rows = []
    for index, point in enumerate(clock.timestamps):
        local = index % per_day
        active = point.date() == DAYS[1]
        rows.append(
            dict(
                timestamp=point,
                phase="continuous",
                symbol=SYMBOL,
                status="trading",
                open=opens[local] if active and local < len(opens) else 10,
                close=closes[local] if active and local < len(closes) else 10,
                high=10.3,
                low=9.7,
                volume=50_000,
                upper_limit=11,
                lower_limit=9,
            )
        )
    overrides = (
        [
            RuleOverride(
                symbol=SYMBOL,
                start=DAYS[1],
                end=DAYS[1],
                changes={"settlement_days": 0},
                reason="测试同日两次往返的 T+0 假设",
                source="人工研究情景",
                version="t0-demo-1",
            )
        ]
        if mode == "t0"
        else []
    )
    profile = "sse_gold_etf" if mode == "native" else "sse_equity_etf"
    return MarketData.from_minutes(
        rows,
        calendar=DAYS,
        frequency=frequency,
        instruments=[Instrument(symbol=SYMBOL, kind="etf")],
        rules=china_rules({SYMBOL: profile}, start=DAYS[0], end=DAYS[-1], overrides=overrides),
        source="人工分钟价格、信号、成交量与边界；不代表真实市场收益",
    )


def round_trips(ctx: Context) -> None:
    """已完成 bar 收盘价低于 10 买入，高于 10 时尝试卖出持仓。"""
    if ctx.session != DAYS[1]:
        return
    close = ctx.history(SYMBOL, bars=1)[-1]
    quantity = ctx.account.positions[SYMBOL].quantity
    if close < 10 and quantity == 0:
        ctx.order(SYMBOL, 1000)
    elif close > 10 and quantity >= 1000:
        ctx.order(SYMBOL, -1000)


def inventory_t(ctx: Context) -> None:
    """先建立昨日底仓；次日卖高买低，买回股份仍受 T+1 约束。"""
    if ctx.bar_index == 0:
        ctx.order(SYMBOL, 1000)
    if ctx.session != DAYS[1]:
        return
    close = ctx.history(SYMBOL, bars=1)[-1]
    quantity = ctx.account.positions[SYMBOL].quantity
    if close > 10 and quantity >= 1000:
        ctx.order(SYMBOL, -1000)
    elif close < 10 and quantity == 0:
        ctx.order(SYMBOL, 1000)


def run_case(
    mode: str, backend: Literal["python", "numba"] = "python", frequency: str = "1min"
) -> BacktestResult:
    config = RunConfig(
        initial_cash=100_000,
        costs=Costs(commission=".0003", minimum_commission=1),
        execution=BarExecution(participation=".1", slippage=FixedTicks(1)),
        backend=backend,
    )
    strategy = inventory_t if mode == "inventory" else round_trips
    return Backtest(sample(mode, frequency), config=config).run(strategy)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("python", "numba"), default="python")
    parser.add_argument("--frequency", choices=("1min", "5min"), default="1min")
    args = parser.parse_args()
    print("人工案例，只验证规则与账本，不代表真实策略收益。")
    for mode in MODES:
        result = run_case(mode, args.backend, args.frequency)
        fees = (
            sum(
                f.commission_units + f.stamp_duty_units + f.transfer_fee_units for f in result.fills
            )
            / 10000
        )
        print(mode, [(str(fill.timestamp), fill.quantity, fill.price) for fill in result.fills])
        print(
            "期末权益：",
            f"{result.equity[-1]:.2f}",
            "持仓：",
            result.holdings[-1, 0],
            "可卖：",
            result.sellable[-1, 0],
            "费用：",
            f"{fees:.2f}",
        )


if __name__ == "__main__":
    main()
