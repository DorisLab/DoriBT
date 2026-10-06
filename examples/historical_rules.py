"""结合 2022 年公开分配事实与人工价格验证账本。

仅发行人的公司行动和有日期的市场规则来自历史事实，OHLC 为人工构造。
本示例不代表 301005.SZ 的真实历史收益。
"""

import argparse
from decimal import Decimal

from doribt import (
    Backtest,
    Context,
    CorporateAction,
    Instrument,
    MarketData,
    PriceAdjustment,
    RunConfig,
    china_rules,
)

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
        adjustments=[
            PriceAdjustment(
                action_id=action.action_id,
                factor=Decimal(10) / Decimal("18.5"),
                known_on="2022-06-09",
                source="synthetic reference ratio: (18.5 - .5) / (1 + .8) / 18.5",
            )
        ],
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
    data = sample()
    config = RunConfig(initial_cash=20000, backend=args.backend)
    result = Backtest(data, config=config).run(sell_on_ex_date)
    print("使用人工价格与公开公司行动事实，不代表真实历史收益。")
    for fill in result.fills:
        print(
            fill.session,
            fill.quantity,
            fill.price,
            fill.commission,
            fill.stamp_duty,
            fill.transfer_fee,
        )
    print("现金分红：", result.entitlements[0].cash_units / 10000)
    print("股息税：", result.stats()["dividend_tax"])
    print("期末现金／权益：", result.cash[-1], result.equity[-1])
    print("原始收盘价：", data.prices("close")[:, 0])
    print(
        "按决策时点复权的收盘价：",
        data.prices("close", adjustment="asof", as_of="2022-06-10")[:, 0],
    )


if __name__ == "__main__":
    main()
