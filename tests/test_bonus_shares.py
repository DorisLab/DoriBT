import numpy as np
import pytest
from corporate_fixtures import distribution, market_with_actions

from doribt import Backtest, Costs, WeightTargets

FREE = Costs(commission=0, minimum_commission=0)


def bonus(**changes):
    values = dict(
        cash_per_share=0,
        pay_date=None,
        bonus_per_share=1,
        share_credit_date="2025-01-07",
        share_listing_date="2025-01-08",
        taxable_bonus_amount_per_share=0,
    )
    return distribution(**(values | changes))


def test_pending_shares_valuation_credit_and_unlock_are_distinct(backend):
    data = market_with_actions([10, 10, 5, 5, 5], [bonus()])
    result = Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [1] * 5}), backend=backend
    )
    np.testing.assert_array_equal(result.holdings[:, 0], [0, 1000, 1000, 2000, 2000])
    np.testing.assert_array_equal(result.pending_shares[:, 0], [0, 0, 1000, 0, 0])
    np.testing.assert_array_equal(result.sellable[:, 0], [0, 0, 1000, 1000, 2000])
    np.testing.assert_array_equal(result.equity, [10000] * 5)


def test_same_day_credit_offsets_sales_in_tax_fifo(backend):
    action = bonus(
        cash_per_share=1,
        pay_date="2025-01-08",
        share_credit_date="2025-01-06",
        share_listing_date="2025-01-06",
    )
    data = market_with_actions([11, 11, 5, 5, 5], [action])

    def strategy(ctx):
        if ctx.session == data.sessions[0]:
            ctx.order("A", 1000)
        elif ctx.session == data.sessions[1]:
            ctx.order("A", -1000)
        elif ctx.session == data.sessions[2]:
            ctx.order("A", -1000)

    result = Backtest(data, initial_cash=11000, costs=FREE).run(strategy, backend=backend)
    # Credit 1,000 and sell 1,000 on Jan 6: no net tax disposal that day.
    assert [str(tax.assessed) for tax in result.taxes] == ["2025-01-07"]
    assert result.taxes[0].amount_units == 2_000_000
    assert result.equity[-1] == 10800


def test_taxable_bonus_and_cash_use_explicit_income_base(backend):
    action = bonus(
        cash_per_share=1,
        pay_date="2025-01-08",
        bonus_per_share=".5",
        taxable_bonus_amount_per_share=".5",
    )
    data = market_with_actions([10, 10, 6, 6, 6], [action])
    result = Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [1, 0, 0, 0, 0]}), backend=backend
    )
    assert result.taxes[0].amount_units == 3_000_000
    assert result.stats()["dividend_tax"] == 300
    assert result.equity[-1] == 9700


def test_pending_target_adjusts_for_bonus_and_includes_uncredited_shares(backend):
    data = market_with_actions([10, 10, 5, 5, 5], [bonus()])

    def strategy(ctx):
        if ctx.session == data.sessions[0]:
            ctx.target_positions({"A": 2000})

    result = Backtest(data, initial_cash=10000, costs=FREE).run(strategy, backend=backend)
    target = result.intents[0]
    assert target.quantity == 4000
    assert (target.adjustments[0].before, target.adjustments[0].after) == (2000, 4000)
    assert result.orders[1].quantity == 2000  # 4,000 - (1,000 registered + 1,000 pending).


def test_integer_odd_lot_can_be_fully_liquidated(backend):
    action = bonus(
        bonus_per_share=".01", share_credit_date="2025-01-06", share_listing_date="2025-01-07"
    )
    data = market_with_actions([10] * 5, [action])

    def strategy(ctx):
        if ctx.session == data.sessions[0]:
            ctx.target_positions({"A": 100})
        elif ctx.session == data.sessions[1]:
            ctx.target_positions({"A": 0})

    result = Backtest(data, costs=FREE).run(strategy, backend=backend)
    assert [f.quantity for f in result.fills] == [100, -100, -1]
    assert result.holdings[-1, 0] == 0


@pytest.mark.parametrize(
    "action,message",
    [
        (bonus(bonus_per_share=".0001"), "fractional share allocation"),
        (bonus(taxable_bonus_amount_per_share=None), "taxable bonus amount is required"),
        (distribution(kind="merger", cash_per_share=0, pay_date=None), "unsupported merger"),
    ],
)
def test_unsupported_entitlements_fail_with_identity(backend, action, message):
    data = market_with_actions([10] * 5, [action])
    with pytest.raises(ValueError, match=message):
        Backtest(data, initial_cash=10000, costs=FREE).run(
            WeightTargets(sessions=data.sessions, weights={"A": [1] * 5}), backend=backend
        )


def test_unheld_unsupported_event_is_not_an_automatic_portfolio_failure(backend):
    action = distribution(kind="rights_issue", cash_per_share=0, pay_date=None)
    data = market_with_actions([10] * 5, [action])
    result = Backtest(data).run(lambda ctx: None, backend=backend)
    assert result.equity[-1] == 100000


def test_unknown_event_cannot_ignore_an_unpaid_claim_after_liquidation(backend):
    unknown = distribution(
        action_id="unknown",
        kind="merger",
        cash_per_share=0,
        pay_date=None,
        record_date="2025-01-06",
        ex_date="2025-01-07",
    )
    data = market_with_actions([10, 10, 9, 9, 9], [distribution(), unknown])
    with pytest.raises(ValueError, match="unsupported merger: unknown"):
        Backtest(data, initial_cash=10000, costs=FREE).run(
            WeightTargets(sessions=data.sessions, weights={"A": [1, 0, 0, 0, 0]}), backend=backend
        )


def test_sample_end_preserves_uncredited_shares(backend):
    data = market_with_actions([10, 10, 5], [bonus()])
    result = Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [1, 1, 1]}), backend=backend
    )
    assert result.equity[-1] == 10000
    assert result.pending_shares[-1, 0] == 1000
    assert result.holdings[-1, 0] == 1000
    assert not result.entitlements[0].shares_credited


@pytest.mark.parametrize("credit", ["2025-01-06", "2025-01-07"])
def test_bonus_cannot_bypass_registered_or_economic_position_bounds(backend, credit):
    data = market_with_actions(
        [10, 10, 5], [bonus(share_credit_date=credit, share_listing_date="2025-01-07")]
    )
    with pytest.raises(OverflowError, match="share quantity exceeds"):
        Backtest(data, initial_cash=6_000_000_000, costs=FREE).run(
            WeightTargets(sessions=data.sessions, weights={"A": [1, 1, 1]}), backend=backend
        )
