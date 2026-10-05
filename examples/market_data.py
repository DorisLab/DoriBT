"""Validate a tiny fictional multi-security market without downloading data."""

from doribt import CorporateAction, Instrument, MarketData, RuleBook, RulePeriod, TradingRule


def sample_data() -> MarketData:
    sessions = ["2025-01-02", "2025-01-03", "2025-01-06"]
    instruments = [Instrument(symbol="STOCK", kind="stock"), Instrument(symbol="ETF", kind="etf")]
    # Illustrative rules only. A real adapter supplies sourced historical periods.
    rule = TradingRule(
        price_tick="0.01",
        buy_minimum=100,
        buy_step=100,
        sell_step=100,
        settlement_days=1,
        stamp_duty_sell="0.0005",
        transfer_fee="0.00001",
    )
    rules = RuleBook(
        tuple(
            RulePeriod(
                symbol=item.symbol,
                start=sessions[0],
                end=sessions[-1],
                rule=rule,
                source="fictional example",
                version="1",
            )
            for item in instruments
        )
    )
    rows = [
        dict(
            session=session,
            symbol=item.symbol,
            status="trading",
            open=10,
            high=11,
            low=9.5,
            close=10.5,
            volume=100_000,
            upper_limit=12,
            lower_limit=8,
        )
        for session in sessions
        for item in instruments
    ]
    action = CorporateAction(
        action_id="stock-dividend",
        symbol="STOCK",
        kind="distribution",
        announced="2025-01-01",
        record_date="2025-01-03",
        ex_date="2025-01-06",
        cash_per_share="0.1",
        pay_date="2025-01-08",
        source="fictional announcement",
    )
    return MarketData.from_records(
        rows,
        calendar=sessions,
        instruments=instruments,
        rules=rules,
        actions=[action],
        source="fictional data v1",
    )


if __name__ == "__main__":
    data = sample_data()
    print("Securities:", data.symbols)
    print("Close prices (yuan):\n", data.prices("close"))
    print("Data identity:", data.fingerprint)
