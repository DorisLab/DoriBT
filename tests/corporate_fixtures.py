from doribt import CorporateAction, Instrument, MarketData, RuleBook, RulePeriod, TradingRule

DATES = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09"]


def distribution(**changes):
    values = dict(
        action_id="d1",
        symbol="A",
        kind="distribution",
        announced="2025-01-01",
        record_date="2025-01-03",
        ex_date="2025-01-06",
        cash_per_share=1,
        pay_date="2025-01-08",
        source="fictional announcement",
    )
    return CorporateAction(**(values | changes))


def market_with_actions(prices, actions, *, dates=None, kind="stock", b=None):
    sessions = DATES[: len(prices)] if dates is None else dates
    values = {"A": prices} if b is None else {"A": prices, "B": b}
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
                source="fictional rules",
                version="1",
            )
            for symbol in values
        )
    )
    rows = [
        dict(
            session=session,
            symbol=symbol,
            status="trading",
            open=path[i],
            high=path[i],
            low=path[i],
            close=path[i],
            volume=100_000,
            upper_limit=None,
            lower_limit=None,
        )
        for i, session in enumerate(sessions)
        for symbol, path in values.items()
    ]
    return MarketData.from_records(
        rows,
        calendar=sessions,
        source="fixture",
        rules=rules,
        instruments=[Instrument(symbol=symbol, kind=kind) for symbol in values],
        actions=actions,
    )
