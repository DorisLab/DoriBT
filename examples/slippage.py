"""在高点买入、低点卖出的人工行情中，对比三种滑点边界策略。"""

import argparse

from doribt import Backtest, Context, Instrument, MarketData, RunConfig, china_rules


def sample() -> MarketData:
    days = ["2025-01-02", "2025-01-03", "2025-01-06"]
    return MarketData.from_records(
        [
            dict(
                session=day,
                symbol="DEMO",
                status="trading",
                open=10,
                high=10,
                low=10,
                close=10,
                volume=100_000,
                upper_limit=11,
                lower_limit=9,
            )
            for day in days
        ],
        calendar=days,
        instruments=[Instrument(symbol="DEMO", kind="etf")],
        rules=china_rules({"DEMO": "szse_equity_etf"}, start=days[0], end=days[-1]),
        source="人工三日平价行情，仅用于说明滑点成本",
    )


def strategy(ctx: Context) -> None:
    ctx.target_positions({"DEMO": 100 if ctx.bar_index == 0 else 0})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    args = parser.parse_args()
    data = sample()
    for policy in ("strict", "cap", "cost"):
        config = RunConfig.from_dict(
            {
                "initial_cash": 10000,
                "commission": 0,
                "minimum_commission": 0,
                "slippage_kind": "bps",
                "slippage_value": 20,
                "slippage_policy": policy,
                "backend": args.backend,
            }
        )
        result = Backtest(data, config=config).run(strategy)
        print(f"边界策略：{policy}；成交价：{[f.price for f in result.fills]}")
        print(f"期末权益：{result.equity[-1]:.2f} 元")
        for fill in result.fills:
            print(f"参考价：{fill.reference_price}；已计入的滑点成本：{fill.slippage_cost} 元")


if __name__ == "__main__":
    main()
