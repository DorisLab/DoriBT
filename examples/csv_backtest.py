"""读取工作目录的 bars.csv；配套数据见文档的行情教程。"""

from doribt import Backtest, Context, Instrument, MarketData, RunConfig, china_rules

days = ["2025-01-02", "2025-01-03", "2025-01-06"]
data = MarketData.from_csv(
    "bars.csv",
    calendar=days,
    instruments=[Instrument(symbol="DEMO", kind="etf")],
    rules=china_rules({"DEMO": "szse_equity_etf"}, start=days[0], end=days[-1]),
    source="行情教程的人工 CSV",
)


def strategy(ctx: Context) -> None:
    ctx.target_weights({"DEMO": 0.9})


result = Backtest(data, config=RunConfig(initial_cash=10_000)).run(strategy)
print("期末权益：", result.equity[-1])
