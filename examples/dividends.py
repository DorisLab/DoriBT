"""人工股票分配示例：现金与股份在不同日期到账。"""

import argparse

from doribt import (
    Backtest,
    Context,
    CorporateAction,
    Costs,
    Instrument,
    MarketData,
    RuleBook,
    RulePeriod,
    RunConfig,
    TradingRule,
)


def sample() -> MarketData:
    dates = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08"]
    prices = [10, 10, 6, 6, 6]
    action = CorporateAction(
        action_id="fictional-distribution",
        symbol="STOCK",
        kind="distribution",
        announced="2025-01-01",
        record_date="2025-01-03",
        ex_date="2025-01-06",
        cash_per_share=1,
        pay_date="2025-01-08",
        bonus_per_share=".5",
        share_credit_date="2025-01-07",
        share_listing_date="2025-01-08",
        taxable_bonus_amount_per_share=".5",
        source="人工应税红股公告",
    )
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
        (
            RulePeriod(
                symbol="STOCK",
                start=dates[0],
                end=dates[-1],
                rule=rule,
                source="人工交易规则",
                version="1",
            ),
        )
    )
    rows = [
        dict(
            session=session,
            symbol="STOCK",
            status="trading",
            open=price,
            high=price,
            low=price,
            close=price,
            volume=100_000,
            upper_limit=None,
            lower_limit=None,
        )
        for session, price in zip(dates, prices, strict=True)
    ]
    return MarketData.from_records(
        rows,
        calendar=dates,
        rules=rules,
        source="人工分红送转行情",
        instruments=[Instrument(symbol="STOCK", kind="stock")],
        actions=[action],
    )


def sell_after_record(ctx: Context) -> None:
    if len(ctx.history("STOCK")) == 1:
        ctx.target_positions({"STOCK": 1000})
    else:
        ctx.target_weights({"STOCK": 0})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    args = parser.parse_args()
    config = RunConfig(
        initial_cash=10000,
        costs=Costs(commission=0, minimum_commission=0),
        backend=args.backend,
    )
    result = Backtest(sample(), config=config).run(sell_after_record)
    print("合成示例：价格、日期与交易费用不代表真实证券情况。")
    print("日期         现金   应收分红   应付股息税   权益")
    for i, session in enumerate(result.sessions):
        print(
            session,
            result.cash[i],
            result.dividend_receivable[i],
            result.tax_payable[i],
            result.equity[i],
        )
    print("股息税：", result.stats()["dividend_tax"])
    print("分配权益：", result.entitlements)


if __name__ == "__main__":
    main()
