from doribt import Instrument, MarketData, RuleBook, RulePeriod, TradingRule

DATES = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08"]


def data_for(a, b=None, *, settlement=1, changes=None, rule_changes=None):
    prices = {"A": a} if b is None else {"A": a, "B": b}
    days = DATES[: len(a)]
    inputs = dict(
        price_tick="0.01",
        buy_minimum=100,
        buy_step=100,
        sell_step=100,
        settlement_days=settlement,
        stamp_duty_sell=0,
        transfer_fee=0,
    )
    rule = TradingRule(**(inputs | (rule_changes or {})))
    rules = RuleBook(
        tuple(
            RulePeriod(
                symbol=s, start=days[0], end=days[-1], rule=rule, source="fictional", version="1"
            )
            for s in prices
        )
    )
    rows = [
        dict(
            session=session,
            symbol=symbol,
            status="trading",
            open=values[index],
            close=values[index],
            high=values[index],
            low=values[index],
            volume=100_000,
            upper_limit=None,
            lower_limit=None,
        )
        for index, session in enumerate(days)
        for symbol, values in prices.items()
    ]
    for index, change in (changes or {}).items():
        rows[index].update(change)
    return MarketData.from_records(
        rows,
        calendar=days,
        instruments=[Instrument(symbol=s, kind="stock") for s in prices],
        rules=rules,
        source="fictional",
    )
