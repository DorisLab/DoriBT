from datetime import date

import numpy as np
import pytest
from corporate_fixtures import distribution, market_with_actions

from doribt import Backtest, Costs, WeightTargets

FREE = Costs(commission=0, minimum_commission=0)


def test_receivable_is_valued_but_only_pay_date_funds_buys(backend):
    data = market_with_actions([10, 10, 9, 9, 9], [distribution()])
    result = Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [1] * 5}), backend=backend
    )
    np.testing.assert_array_equal(result.equity, [10000] * 5)
    np.testing.assert_array_equal(result.dividend_receivable, [0, 0, 1000, 1000, 0])
    np.testing.assert_array_equal(result.cash, [10000, 0, 0, 0, 1000])
    assert not result.taxes
    assert result.entitlements[0].eligible_quantity == 1000
    assert result.entitlements[0].cash_paid


def test_sell_before_payment_keeps_entitlement_and_accrues_then_pays_tax(backend):
    data = market_with_actions([10, 10, 9, 9, 9], [distribution()])
    result = Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [1, 0, 0, 0, 0]}), backend=backend
    )
    np.testing.assert_array_equal(result.equity, [10000, 10000, 9800, 9800, 9800])
    np.testing.assert_array_equal(result.cash, [10000, 0, 9000, 8800, 9800])
    np.testing.assert_array_equal(result.tax_payable, [0, 0, 200, 0, 0])
    assert result.taxes[0].amount_units == 2_000_000
    assert result.taxes[0].paid_units == 2_000_000
    assert result.tax_payments[0].session == date(2025, 1, 7)
    assert result.stats()["dividend_tax"] == 200


def test_sample_end_keeps_receivables_and_unpaid_tax(backend):
    data = market_with_actions([10, 10, 9], [distribution()])
    result = Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [1, 0, 0]}), backend=backend
    )
    assert result.dividend_receivable[-1] == 1000
    assert result.tax_payable[-1] == 200
    assert result.entitlements[0].pay_date == date(2025, 1, 8)
    assert not result.entitlements[0].cash_paid
    assert result.taxes[0].paid_units == 0


def test_no_entitlement_when_bought_after_record_and_etf_tax_is_not_double_counted(backend):
    data = market_with_actions([10, 10, 9, 9, 9], [distribution()])
    result = Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [0, 1, 1, 1, 1]}), backend=backend
    )
    assert not result.entitlements
    etf = market_with_actions([10, 10, 9, 9, 9], [distribution()], kind="etf")
    result = Backtest(etf, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=etf.sessions, weights={"A": [1, 0, 0, 0, 0]}), backend=backend
    )
    assert not result.taxes
    assert result.cash[-1] == 10000


def test_tax_debt_reserves_sale_proceeds_before_new_buys(backend):
    data = market_with_actions([10, 10, 9, 9, 9], [distribution()], b=[10] * 5)

    def strategy(ctx):
        if ctx.session == data.sessions[0]:
            ctx.order("A", 1000)
        elif ctx.session == data.sessions[1]:
            ctx.target_positions({"A": 0, "B": 900})
        elif ctx.session == data.sessions[2]:
            assert ctx.account.cash == 0
            assert ctx.account.tax_payable == 200
            assert ctx.account.available_cash == 0
            ctx.target_positions({"A": 1000, "B": 0})

    result = Backtest(data, initial_cash=10000, costs=FREE).run(strategy, backend=backend)
    day4 = [fill for fill in result.fills if fill.session == data.sessions[3]]
    assert [(f.symbol, f.quantity) for f in day4] == [("B", -900), ("A", 900)]
    # 9,000 sale proceeds - 8,100 buy - 200 outstanding tax, not 1,000 A shares.
    assert result.cash[3] == 700
    assert result.tax_payable[3] == 0


def test_micro_yuan_dividends_are_aggregated_before_rounding(backend):
    action = distribution(cash_per_share="0.000049")
    data = market_with_actions([10] * 5, [action])
    result = Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [1, 0, 0, 0, 0]}), backend=backend
    )
    assert result.entitlements[0].cash_units == 500  # .049 yuan -> .05 yuan.
    assert result.taxes[0].amount_units == 100  # .0098 yuan -> .01 yuan.
    assert result.cash[-1] == 10000.04


def test_record_date_missing_from_calendar_fails():
    with pytest.raises(ValueError, match="record_date must be"):
        market_with_actions([10] * 5, [distribution(record_date="2025-01-04")])
