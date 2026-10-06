"""安装 doribt 后即可运行；仅使用合成行情与公开 API。"""

from doribt import Backtest, Context, Costs, Instrument, MarketData, RunConfig, china_rules

days = ["2025-01-02", "2025-01-03", "2025-01-06"]
prices = [10, 10, 11]
data = MarketData.from_records(
    [
        {
            "session": day,
            "symbol": "DEMO",
            "status": "trading",
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 500_000,
            "upper_limit": 12,
            "lower_limit": 8,
        }
        for day, price in zip(days, prices, strict=True)
    ],
    calendar=days,
    instruments=[Instrument(symbol="DEMO", kind="etf")],
    rules=china_rules({"DEMO": "szse_equity_etf"}, start=days[0], end=days[-1]),
    source="人工三日行情，仅用于演示",
)


def buy_and_hold(ctx: Context) -> None:
    ctx.target_weights({"DEMO": 0.9})


config = RunConfig(initial_cash=10_000, costs=Costs(commission=0.0003, minimum_commission=5))
result = Backtest(data, config=config).run(buy_and_hold)
print("期末权益：", result.equity[-1])  # 10895 元：剩余现金 995 + 持仓 900 × 11。
print("总收益率：", result.report().stats["total_return"])
