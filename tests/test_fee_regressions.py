"""Carry the prototype's meaningful money edge cases into the supported API."""

import numpy as np
from engine_fixtures import data_for

from doribt import Backtest, Costs


def test_half_cent_rounds_up_in_formal_ledger(backend):
    data = data_for([2.78] * 3, rule_changes={"price_tick": ".001"})
    result = Backtest(data, initial_cash=110000).run(
        lambda ctx: ctx.target_positions({"A": 37500}) if ctx.bar_index == 0 else None,
        backend=backend,
    )
    assert result.fills[0].commission_units == 312800
    assert result.cash[-1] == 5718.72


def test_full_weight_reserves_fees_and_never_spends_negative_cash(backend):
    result = Backtest(data_for([10] * 3)).run(
        lambda ctx: ctx.target_weights({"A": 1}), backend=backend
    )
    assert result.fills[0].quantity == 9900
    assert result.fills[0].commission == 29.70
    assert np.all(result.cash >= 0)


def test_unaffordable_minimum_and_extreme_rate_leave_cash_nonnegative(backend):
    data = data_for([1] * 3)
    for costs in (Costs(minimum_commission=1001), Costs(commission=1)):
        result = Backtest(data, initial_cash=1000, costs=costs).run(
            lambda ctx: ctx.target_weights({"A": 1}), backend=backend
        )
        assert np.all(result.cash >= 0)
        assert all(fill.quantity > 0 for fill in result.fills)
