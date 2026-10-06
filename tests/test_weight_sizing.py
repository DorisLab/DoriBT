import json
from dataclasses import replace

import numpy as np
import pytest
from engine_fixtures import data_for
from minute_fixtures import minute_data
from test_scheduled import compare

from doribt import Backtest, BarExecution, CorporateAction, Costs, RunConfig, WeightTargets

FREE = Costs(commission=0, minimum_commission=0)


@pytest.mark.parametrize("sizing,shares,cash", [("close", 500, 0), ("execution", 200, 6000)])
def test_sizing_modes_have_independent_gap_expectations(backend, sizing, shares, cash, tmp_path):
    data = data_for([10, 20, 20])
    targets = WeightTargets(sessions=data.timeline, weights={"A": [0.5] * 3}, sizing=sizing)
    result = compare(data, targets, backend, config=RunConfig(initial_cash=10000, costs=FREE))
    assert result.holdings[:, 0].tolist() == [0, shares, shares]
    assert result.cash[-1] == cash
    intent = result.intents[0]
    assert intent.quantity == shares and intent.weight_ppm == 500000
    assert intent.sizing == sizing
    assert intent.sized_at == data.timeline[0 if sizing == "close" else 1]
    result.export(tmp_path / "report")
    ledger = json.loads((tmp_path / "report/ledger.json").read_text(encoding="utf-8"))
    assert ledger["intents"][0]["sizing"] == sizing
    assert result.run_info.to_dict()["strategy"]["inputs"]["sizing"] == sizing


def test_execution_sizing_uses_shared_open_equity_before_any_fill(backend):
    data = data_for([10, 10, 20], [10, 10, 10])

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 500)
        elif ctx.bar_index == 1:
            ctx.target_weights({"B": 0.8}, sizing="execution")

    result = Backtest(data, config=RunConfig(initial_cash=10000, costs=FREE)).run(
        strategy, backend=backend
    )
    # 开盘权益 5000 + 500 * 20 = 15000；先卖 A 后买 B，B = 15000 * 80% / 10。
    assert [f.quantity for f in result.fills] == [500, -500, 1200]
    assert result.holdings[-1].tolist() == [0, 1200]
    assert result.cash[-1] == 3000


def test_execution_sizing_does_not_use_same_bar_close_or_later_open(backend):
    first = data_for([10, 20, 20])
    changed = data_for([10, 20, 30], changes={1: {"close": 5, "low": 5}})

    def strategy(ctx):
        ctx.target_weights({"A": 0.5}, sizing="execution")

    def test(data):
        return Backtest(data, config=RunConfig(initial_cash=10000, costs=FREE)).run(
            strategy, backend=backend
        )

    left, right = test(first), test(changed)
    assert left.fills == right.fills
    assert left.intents == right.intents
    assert left.intents[0].quantity == 200


def test_execution_sizing_is_once_and_partial_fills_keep_quantity(backend):
    data = minute_data(
        days=1, frequency="5min", volume=100, changes={1: {"open": 11}, 2: {"open": 9}}
    )
    targets = WeightTargets(sessions=data.timeline, weights={"A": [0.5] * 48}, sizing="execution")
    result = compare(
        data,
        targets,
        backend,
        initial_cash=10000,
        costs=FREE,
        execution=BarExecution(participation=1),
    )
    assert [f.quantity for f in result.fills] == [100] * 4
    assert result.intents[0].quantity == 400
    assert result.intents[0].sized_at == data.timeline[1]
    assert result.cash[-1] == 6000


def test_sizing_mode_change_and_explicit_rebalance_replace_targets(backend):
    data = data_for([10, 10, 20, 20, 20])

    def strategy(ctx):
        ctx.target_weights(
            {"A": 0.5},
            sizing="close" if ctx.bar_index == 0 else "execution",
            rebalance=ctx.bar_index == 2,
        )

    result = Backtest(data, config=RunConfig(initial_cash=10000, costs=FREE)).run(
        strategy, backend=backend
    )
    assert [i.sizing for i in result.intents] == ["close", "execution", "execution"]
    assert [i.quantity for i in result.intents] == [500, 400, 400]
    assert [f.quantity for f in result.fills] == [500, -100]


def test_deferred_targets_can_be_cancelled_and_last_bar_stays_unexecuted(backend):
    data = data_for([10, 10])

    def strategy(ctx):
        ids = ctx.target_weights({"A": 0.5}, sizing="execution")
        if ctx.bar_index == 0:
            ctx.cancel(ids[0])

    result = Backtest(data, config=RunConfig()).run(strategy, backend=backend)
    assert not result.orders
    assert [i.status for i in result.intents] == ["cancelled", "unexecuted"]
    assert all(i.sized_at is None for i in result.intents)
    assert all(i.quantity is None for i in result.intents)


def test_zero_weight_needs_no_active_price_and_invalid_mode_fails():
    data = data_for([10, None], changes={1: {"status": "delisted", "volume": 0}})
    result = Backtest(data, config=RunConfig()).run(
        lambda ctx: ctx.target_weights({}, sizing="execution")
    )
    assert result.intents[0].status == "fulfilled"
    with pytest.raises(ValueError, match="sizing"):
        WeightTargets(sessions=data.timeline, weights={}, sizing="unknown")
    with pytest.raises(RuntimeError, match="sizing"):
        Backtest(data, config=RunConfig()).run(lambda ctx: ctx.target_weights({}, sizing="bad"))
    with pytest.raises(RuntimeError, match="BarExecution"):
        Backtest(data_for([10, 10])).run(lambda ctx: ctx.target_weights({}, sizing="execution"))


def test_execution_sizing_includes_pending_bonus_and_receivable_before_trading(backend):
    data = data_for([10, 10, 5, 5])
    action = CorporateAction(
        action_id="bonus",
        symbol="A",
        kind="distribution",
        announced="2025-01-02",
        record_date="2025-01-03",
        ex_date="2025-01-06",
        pay_date="2025-01-08",
        share_credit_date="2025-01-07",
        share_listing_date="2025-01-07",
        cash_per_share=1,
        bonus_per_share=1,
        taxable_bonus_amount_per_share=0,
        source="人工权益",
    )
    data = replace(data, actions=(action,))

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 500)
        if ctx.bar_index == 1:
            ctx.target_weights({"A": 0.5}, sizing="execution")

    result = Backtest(data, config=RunConfig(initial_cash=10000, costs=FREE)).run(
        strategy, backend=backend
    )
    # 待入账送股参与估值和已有数量；应收分红计入权益但不能买入。
    assert result.intents[0].quantity == 1000
    assert result.intents[0].adjustments == ()
    assert [f.quantity for f in result.fills] == [500]
    assert result.holdings[-1, 0] == 1000
    assert result.dividend_receivable[-1] == 500
    assert np.all(result.cash_units == [100000000, 50000000, 50000000, 50000000])


def test_execution_weight_reservations_use_same_open_for_all_securities(backend):
    data = data_for([20, 10, 10], [10, 20, 20])
    targets = WeightTargets(
        sessions=data.timeline, weights={"A": [0.5] * 3, "B": [0.5] * 3}, sizing="execution"
    )
    result = compare(data, targets, backend, config=RunConfig(initial_cash=10000, costs=FREE))
    assert result.holdings[1].tolist() == [500, 200]
    assert result.cash[1] == 1000
    assert [f.session for f in result.fills] == [data.sessions[1]] * 2


@pytest.mark.parametrize("blocked", ["suspended", "limit"])
def test_blocked_open_sizes_once_and_does_not_resize_on_retry(backend, blocked):
    change = (
        {"status": "suspended", "volume": 0}
        if blocked == "suspended"
        else {"upper_limit": 20, "lower_limit": 10}
    )
    data = data_for([10, 20, 10], changes={1: change})
    targets = WeightTargets(sessions=data.timeline, weights={"A": [0.5] * 3}, sizing="execution")
    result = compare(data, targets, backend, config=RunConfig(initial_cash=10000, costs=FREE))
    assert result.holdings[:, 0].tolist() == [0, 0, 200]
    assert result.intents[0].quantity == 200
    assert result.intents[0].sized_at == data.timeline[1]
    assert result.cash[-1] == 8000


def test_resolved_buy_target_survives_inactive_rows_without_creating_invalid_children(backend):
    data = data_for(
        [10, 20, None, None],
        changes={
            1: {"upper_limit": 20, "lower_limit": 10},
            2: {"status": "delisted", "volume": 0},
            3: {"status": "delisted", "volume": 0},
        },
    )
    targets = WeightTargets(sessions=data.timeline, weights={"A": [0.5] * 4}, sizing="execution")
    result = compare(data, targets, backend, config=RunConfig(initial_cash=10000, costs=FREE))
    assert not result.fills
    assert result.intents[0].quantity == 200
    assert result.intents[0].status == "unexecuted"
