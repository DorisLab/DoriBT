"""Published 2022 distribution facts with artificial prices for ledger verification.

This is NOT a historical return for 301005.SZ. Only the issuer's action facts and
the market's dated rules are historical; OHLC values below are deliberately made up.
"""

import argparse

from doribt import Backtest, Context, CorporateAction, Instrument, MarketData, china_rules

SOURCE = (
    "https://disc.static.szse.cn/disc/disk03/finalpage/2022-06-02/"
    "b634197f-aefd-410a-b0e9-936c060e09e7.PDF"
)
SYMBOL = "301005.SZ"


def sample() -> MarketData:
    dates = ["2022-06-08", "2022-06-09", "2022-06-10", "2022-06-13"]
    prices = ["18.5", "18.5", "10", "10"]
    boundaries = [("22.2", "14.8")] * 2 + [("12", "8")] * 2
    action = CorporateAction(
        action_id="301005-2021-annual",
        symbol=SYMBOL,
        kind="distribution",
        announced="2022-06-02",
        record_date="2022-06-09",
        ex_date="2022-06-10",
        cash_per_share=".5",
        pay_date="2022-06-10",
        bonus_per_share=".8",
        taxable_bonus_amount_per_share=0,
        share_credit_date="2022-06-10",
        share_listing_date="2022-06-10",
        source=SOURCE,
    )
    rows = [
        dict(
            session=session,
            symbol=SYMBOL,
            status="trading",
            open=price,
            high=price,
            low=price,
            close=price,
            volume=100_000,
            upper_limit=upper,
            lower_limit=lower,
        )
        for session, price, (upper, lower) in zip(dates, prices, boundaries, strict=True)
    ]
    return MarketData.from_records(
        rows,
        calendar=dates,
        instruments=[Instrument(symbol=SYMBOL, kind="stock")],
        rules=china_rules({SYMBOL: "szse_chinext"}, start=dates[0], end=dates[-1]),
        actions=[action],
        source="artificial OHLC, volume and bounds; sourced issuer action and market rules",
    )


def sell_on_ex_date(ctx: Context) -> None:
    if ctx.session.isoformat() == "2022-06-08":
        ctx.order(SYMBOL, 1000)
    elif ctx.session.isoformat() == "2022-06-09":
        ctx.target_positions({SYMBOL: 0})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    args = parser.parse_args()
    result = Backtest(sample(), initial_cash=20000).run(sell_on_ex_date, backend=args.backend)
    print("ARTIFICIAL PRICES; published action facts. NOT an actual historical return.")
    for fill in result.fills:
        print(
            fill.session,
            fill.quantity,
            fill.price,
            fill.commission,
            fill.stamp_duty,
            fill.transfer_fee,
        )
    print("Dividend:", result.entitlements[0].cash_units / 10000)
    print("Tax:", result.stats()["dividend_tax"])
    print("Final cash/equity:", result.cash[-1], result.equity[-1])


if __name__ == "__main__":
    main()
