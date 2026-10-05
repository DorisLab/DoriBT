"""Independent Decimal ledger across record, ex, credit, listing, and cash dates."""

from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pytest
from corporate_fixtures import distribution, market_with_actions
from hypothesis import given, settings
from hypothesis import strategies as st

from doribt import Backtest, Costs


@pytest.mark.parametrize("backend", ["python", pytest.param("numba", marks=pytest.mark.numba)])
@settings(max_examples=50, deadline=None, derandomize=True)
@given(
    lots=st.integers(1, 20),
    price=st.integers(2, 30),
    dividend=st.integers(0, 3),
    bonus=st.sampled_from([".25", ".5", "1"]),
    taxable=st.booleans(),
)
def test_entitlement_and_tax_ledger(backend, lots, price, dividend, bonus, taxable):
    quantity, ratio = lots * 100, Decimal(bonus)
    ex_price, cash_dividend = Decimal(price), Decimal(dividend)
    original_price = ex_price * (1 + ratio) + cash_dividend
    taxable_bonus = ratio if taxable else Decimal(0)
    action = distribution(
        cash_per_share=str(cash_dividend),
        pay_date="2025-01-09" if dividend else None,
        bonus_per_share=bonus,
        share_credit_date="2025-01-07",
        share_listing_date="2025-01-08",
        taxable_bonus_amount_per_share=str(taxable_bonus),
    )
    data = market_with_actions([str(original_price)] * 2 + [str(ex_price)] * 4, [action])
    bonus_quantity = int(quantity * ratio)

    def strategy(ctx):
        if ctx.session == data.sessions[0]:
            ctx.order("A", quantity)
        elif ctx.session == data.sessions[1]:
            ctx.order("A", -quantity)
        elif ctx.session == data.sessions[3]:
            ctx.order("A", -bonus_quantity)

    capital = original_price * quantity
    result = Backtest(
        data, initial_cash=str(capital), costs=Costs(commission=0, minimum_commission=0)
    ).run(strategy, backend=backend)
    tax = ((cash_dividend + taxable_bonus) * quantity * Decimal(".2")).quantize(
        Decimal(".01"), ROUND_HALF_UP
    )
    dividend_total = cash_dividend * quantity
    sale = quantity * ex_price
    bonus_sale = bonus_quantity * ex_price
    cash = [
        capital,
        Decimal(0),
        sale,
        sale - tax,
        sale + bonus_sale - tax,
        sale + bonus_sale - tax + dividend_total,
    ]
    receivable = [
        Decimal(0),
        Decimal(0),
        dividend_total,
        dividend_total,
        dividend_total,
        Decimal(0),
    ]
    tax_due = [Decimal(0), Decimal(0), tax, Decimal(0), Decimal(0), Decimal(0)]
    np.testing.assert_array_equal(result.cash_units, [int(value * 10000) for value in cash])
    np.testing.assert_array_equal(
        result.dividend_receivable_units, [int(value * 10000) for value in receivable]
    )
    np.testing.assert_array_equal(
        result.tax_payable_units, [int(value * 10000) for value in tax_due]
    )
    assert result.equity[-1] == float(capital - tax)
    assert sum(p.amount_units for p in result.tax_payments) == int(tax * 10000)
    assert not result.tax_lots
