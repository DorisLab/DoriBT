"""Small fictional market; no downloaded prices or market-rule claims."""

from doribt import Instrument, MarketData, RuleBook, RulePeriod, TradingRule

SESSIONS = ["2025-01-02", "2025-01-03", "2025-01-06"]
INSTRUMENTS = [Instrument(symbol="A", kind="stock"), Instrument(symbol="B", kind="etf")]


def rule(**changes):
    values = dict(
        price_tick="0.01",
        buy_minimum=100,
        buy_step=100,
        sell_step=100,
        settlement_days=1,
        stamp_duty_sell="0.0005",
        transfer_fee="0.00001",
    )
    return TradingRule(**(values | changes))


def rules():
    return RuleBook(
        tuple(
            RulePeriod(
                symbol=item.symbol,
                start=SESSIONS[0],
                end=SESSIONS[-1],
                rule=rule(),
                source="fictional test",
                version="v1",
            )
            for item in INSTRUMENTS
        )
    )


def records():
    return [
        dict(
            session=session,
            symbol=item.symbol,
            status="trading",
            open="10.00",
            high="11.00",
            low="9.50",
            close="10.50",
            volume=10_000,
            upper_limit="12.00",
            lower_limit="8.00",
        )
        for session in SESSIONS
        for item in INSTRUMENTS
    ]


def market(rows=None, **changes):
    values = dict(calendar=SESSIONS, instruments=INSTRUMENTS, rules=rules(), source="fixture")
    return MarketData.from_records(records() if rows is None else rows, **(values | changes))


def inactive(row, status):
    return row | dict(
        status=status,
        open=None,
        high=None,
        low=None,
        close=None,
        volume=0,
        upper_limit=None,
        lower_limit=None,
    )
