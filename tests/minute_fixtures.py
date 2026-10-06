from datetime import date

from doribt import Instrument, MarketData, RuleBook, RulePeriod, TradingRule
from doribt.clock import MinuteClock


def minute_data(
    *,
    days=2,
    volume=1000,
    settlement=1,
    changes=None,
    frequency="1min",
    actions=(),
    symbols=("A",),
    rule_changes=None,
):
    calendar = (date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6))[:days]
    clock = MinuteClock.build(calendar, frequency)
    rule = TradingRule(
        **(
            dict(
                price_tick=".01",
                buy_minimum=100,
                buy_step=100,
                sell_step=100,
                settlement_days=settlement,
                stamp_duty_sell=0,
                transfer_fee=0,
            )
            | (rule_changes or {})
        )
    )
    rules = RuleBook(
        tuple(
            RulePeriod(
                symbol=s,
                start=calendar[0],
                end=calendar[-1],
                rule=rule,
                source="synthetic",
                version="1",
            )
            for s in symbols
        )
    )
    rows = [
        dict(
            timestamp=point,
            phase="continuous",
            symbol=symbol,
            status="trading",
            open=10,
            close=10,
            high=11,
            low=9,
            volume=volume,
            upper_limit=12,
            lower_limit=8,
        )
        for point in clock.timestamps
        for symbol in symbols
    ]
    for index, change in (changes or {}).items():
        rows[index].update(change)
    return MarketData.from_minutes(
        rows,
        calendar=calendar,
        frequency=frequency,
        instruments=[Instrument(symbol=s, kind="stock") for s in symbols],
        rules=rules,
        source="synthetic minute fixture",
        actions=actions,
    )
