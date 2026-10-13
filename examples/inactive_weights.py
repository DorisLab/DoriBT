"""六日两证券示例：保留未上市空行情，零目标不需要历史规则。"""

import argparse

from doribt import (
    Backtest,
    BarExecution,
    Costs,
    Instrument,
    MarketData,
    RuleBook,
    RulePeriod,
    TradingRule,
    WeightTargets,
)


def make_data(*, full_rules: bool = False) -> MarketData:
    days = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09"]
    rule = TradingRule(
        price_tick=".01",
        buy_minimum=100,
        buy_step=100,
        sell_step=100,
        settlement_days=0,
        stamp_duty_sell=0,
        transfer_fee=0,
    )
    rules = RuleBook(
        tuple(
            RulePeriod(
                symbol=symbol,
                start=days[0 if full_rules or symbol == "B" else 2],
                end=days[-1],
                rule=rule,
                source="人工示例",
                version="1",
            )
            for symbol in ("A", "B")
        )
    )
    rows = []
    for index, session in enumerate(days):
        for symbol in ("A", "B"):
            active = symbol == "B" or index >= 2
            price = 10 if active else None
            rows.append(
                dict(
                    session=session,
                    symbol=symbol,
                    status="trading" if active else "unlisted",
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=100_000 if active else 0,
                    upper_limit=None,
                    lower_limit=None,
                )
            )
    return MarketData.from_records(
        rows,
        calendar=days,
        instruments=[Instrument(symbol=s, kind="etf") for s in ("A", "B")],
        rules=rules,
        source="人工六日行情；A 在第三日上市",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    args = parser.parse_args()
    data = make_data()
    targets = WeightTargets(
        sessions=data.timeline, weights={"A": [0, 0, 0.5, 0.5, 0, 0], "B": [0.5] * 6}
    )
    result = Backtest(
        data,
        initial_cash=10_000,
        costs=Costs(commission=0, minimum_commission=0),
        execution=BarExecution(),
    ).run(targets, backend=args.backend)
    print("执行计划：", result.run_info.to_dict()["execution_plan"])
    print("成交：", [(fill.session, fill.symbol, fill.quantity) for fill in result.fills])
    print("期末持仓：", result.holdings[-1].tolist())


if __name__ == "__main__":
    main()
