"""用人工跳空行情说明股数目标、权重定量和明确的支出上限。"""

import argparse
from collections.abc import Callable

from doribt import Backtest, Context, Costs, Instrument, MarketData, RunConfig, china_rules


def sample() -> MarketData:
    days = ["2025-01-02", "2025-01-03", "2025-01-06"]
    return MarketData.from_records(
        [
            dict(
                session=day,
                symbol="DEMO",
                status="trading",
                open=price,
                high=price,
                low=price,
                close=price,
                volume=100_000,
                upper_limit=None,
                lower_limit=None,
            )
            for day, price in zip(days, [10, 10.2, 10.2], strict=True)
        ],
        calendar=days,
        instruments=[Instrument(symbol="DEMO", kind="etf")],
        rules=china_rules({"DEMO": "szse_equity_etf"}, start=days[0], end=days[-1]),
        source="人工跳空行情，仅用于演示定量与预算",
    )


def fixed_shares(ctx: Context) -> None:
    if ctx.bar_index == 0:
        ctx.target_positions({"DEMO": 500})


def close_weight(ctx: Context) -> None:
    if ctx.bar_index == 0:
        ctx.target_weights({"DEMO": 0.5})


def execution_weight(ctx: Context) -> None:
    if ctx.bar_index == 0:
        ctx.target_weights({"DEMO": 0.5}, sizing="execution")


def capped_order(ctx: Context) -> None:
    if ctx.bar_index == 0:
        ctx.order("DEMO", 500, max_spend=5000)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    args = parser.parse_args()
    engine = Backtest(
        sample(),
        config=RunConfig(
            initial_cash=10000,
            costs=Costs(commission=0, minimum_commission=0),
            backend=args.backend,
        ),
    )
    cases: list[tuple[str, Callable[[Context], None], int, float]] = [
        ("固定 500 份", fixed_shares, 500, 4900),
        ("50% 收盘定量", close_weight, 500, 4900),
        ("50% 开盘定量", execution_weight, 400, 5920),
        ("500 份且最多支出 5000 元", capped_order, 490, 5002),
    ]
    for name, strategy, shares, cash in cases:
        result = engine.run(strategy)
        if result.holdings[-1, 0] != shares or result.cash[-1] != cash:
            raise RuntimeError(f"{name} 的手算预期不符")
        print(f"{name}：持仓 {shares} 份，现金 {cash:.2f} 元")


if __name__ == "__main__":
    main()
