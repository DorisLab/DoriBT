"""Synthetic 1-minute orders with shared volume, T+1 and cumulative commission."""

import argparse
from datetime import date

from doribt import Backtest, BarExecution, Context, FixedTicks, Instrument, MarketData, china_rules
from doribt.clock import MinuteClock


def sample() -> MarketData:
    days = (date(2025, 1, 2), date(2025, 1, 3))
    clock = MinuteClock.build(days, "1min")
    rows = [
        dict(
            timestamp=point,
            phase="continuous",
            symbol="DEMO",
            status="trading",
            open=10,
            high=10.1,
            low=9.9,
            close=10,
            volume=1000,
            upper_limit=12,
            lower_limit=8,
        )
        for point in clock.timestamps
    ]
    return MarketData.from_minutes(
        rows,
        calendar=days,
        instruments=[Instrument(symbol="DEMO", kind="etf")],
        rules=china_rules({"DEMO": "szse_equity_etf"}, start=days[0], end=days[-1]),
        source="fictional two-day minute example",
    )


def strategy(ctx: Context) -> None:
    if ctx.bar_index == 0:
        ctx.order("DEMO", 1000, valid_for="day")
    elif ctx.bar_index == 240:
        ctx.order("DEMO", -1000, valid_for="day")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("python", "numba"), default="python")
    args = parser.parse_args()
    result = Backtest(
        sample(), execution=BarExecution(participation=0.1, slippage=FixedTicks(1))
    ).run(strategy, backend=args.backend)
    print("SYNTHETIC minute data. Fills are known only at each bar's end.")
    for order in result.orders:
        print(order.order_id, order.quantity, order.filled, order.status, order.fees)
    print(
        "Orders:",
        len(result.orders),
        "fills:",
        len(result.fills),
        "final equity:",
        result.equity[-1],
    )


if __name__ == "__main__":
    main()
