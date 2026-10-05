"""Reusable market preparation must never share live account or strategy state."""

from dataclasses import replace

import numpy as np
import pytest
from engine_fixtures import data_for

from doribt import Backtest, Costs

FREE = Costs(commission=0, minimum_commission=0)


def allocated(ctx, *, quantity):
    ctx.target_positions({"A": quantity})


def test_repeated_parameter_runs_have_independent_accounts_and_outputs(backend):
    data = data_for([10, 10, 11, 12])
    run = Backtest(data, initial_cash=10000, costs=FREE)
    first = run.run(allocated, parameters={"quantity": 100}, backend=backend)
    saved = first.equity_units.copy()
    larger = run.run(allocated, parameters={"quantity": 500}, backend=backend)
    flat = run.run(allocated, parameters={"quantity": 0}, backend=backend)
    repeated = run.run(allocated, parameters={"quantity": 100}, backend=backend)
    assert first.equity[-1] == 10200
    assert larger.equity[-1] == 11000
    assert flat.equity[-1] == 10000
    np.testing.assert_array_equal(first.equity_units, saved)
    np.testing.assert_array_equal(repeated.equity_units, saved)
    assert first.orders == repeated.orders and first.run_info == repeated.run_info
    assert not np.shares_memory(first.cash_units, larger.cash_units)
    assert not np.shares_memory(first.holdings, larger.holdings)
    with pytest.raises(ValueError, match="WRITEABLE"):
        first.close_units.setflags(write=True)


def test_replacing_data_or_costs_on_backtest_cannot_reuse_stale_inputs(backend):
    first_data = data_for([10, 10, 11])
    run = Backtest(first_data, initial_cash=10000, costs=FREE)
    first = run.run(allocated, parameters={"quantity": 100}, backend=backend)
    run.data = data_for([20, 20, 25])
    run.costs = Costs(commission=0, minimum_commission=5)
    second = run.run(allocated, parameters={"quantity": 100}, backend=backend)
    assert first.equity[-1] == 10100
    assert second.equity[-1] == 10495
    assert second.fills[0].price == 20
    assert second.fills[0].commission == 5
    assert second.data_fingerprint != first.data_fingerprint
    assert second.run_info.to_dict()["costs"]["minimum_commission_units"] == 50000


def test_cached_fingerprint_tracks_new_immutable_data_instances():
    data = data_for([10, 10, 11])
    original = data.fingerprint
    renamed = replace(data, source="another source")
    assert renamed.fingerprint != original
    assert data.fingerprint == original
    assert data.symbols == ("A",)


def test_bar_index_counts_supplied_sessions_without_copying_history():
    data = data_for([10, 10, 11])
    observed = []

    def observe(ctx):
        observed.append((ctx.bar_index, ctx.session))
        with pytest.raises(AttributeError):
            ctx.bar_index = 99

    Backtest(data).run(observe)
    assert observed == list(enumerate(data.sessions))
