from dataclasses import fields

import numpy as np
import pytest
from minute_fixtures import minute_data

from doribt import (
    Backtest,
    BarExecution,
    CorporateAction,
    Costs,
    FixedBps,
    FixedTicks,
    PositionTargets,
    VolumeImpact,
    WeightTargets,
)
from doribt.kernels.segments import value_span
from doribt.validation import MAX_MONEY


def equal_results(fast, slow):
    for field in fields(fast):
        if field.name == "run_info":
            continue
        left, right = getattr(fast, field.name), getattr(slow, field.name)
        if isinstance(left, np.ndarray):
            np.testing.assert_array_equal(left, right, err_msg=field.name)
        else:
            assert left == right, field.name
    assert fast.run_info.to_dict()["execution_path"] == "scheduled_segments"
    assert slow.run_info.to_dict()["execution_path"] == "bar_callbacks"


def compare(data, targets, backend, **kwargs):
    test = Backtest(data, **kwargs)
    fast = test.run(targets, backend=backend)
    slow = test.run(lambda ctx: targets(ctx), backend=backend)
    equal_results(fast, slow)
    return fast


@pytest.mark.parametrize("settlement", [0, 1, 2])
@pytest.mark.parametrize("slippage", [FixedTicks(1), FixedBps(5), VolumeImpact(0.2)])
def test_scheduled_shared_cash_partial_fills_and_replacements(backend, settlement, slippage):
    data = minute_data(
        days=3,
        symbols=("A", "B"),
        volume=1200,
        settlement=settlement,
        changes={i: {"volume": 0} for i in range(36, 120)},
        rule_changes={"order_maximum": 500, "transfer_fee": 0.00001, "stamp_duty_sell": 0.0005},
    )
    a, b = np.zeros(720, dtype=int), np.zeros(720, dtype=int)
    a[1:235], a[235:246], b[240:486], a[486:] = 1400, 333, 2000, 500
    result = compare(
        data,
        PositionTargets(sessions=data.timeline, quantities={"B": b, "A": a}),
        backend,
        initial_cash=11000,
        execution=BarExecution(participation=0.017, slippage=slippage),
    )
    assert result.fills and any(o.status == "cancelled" for o in result.orders)


@pytest.mark.parametrize("policy", ["strict", "cap", "cost"])
def test_scheduled_boundary_policy_matches_callbacks_with_partial_fills(backend, policy):
    data = minute_data(frequency="5min", changes={i: {"high": 10, "low": 10} for i in range(96)})
    targets = PositionTargets(sessions=data.timeline, quantities={"A": [200] * 47 + [0] * 49})
    result = compare(
        data,
        targets,
        backend,
        initial_cash=10000,
        costs=Costs(commission=0, minimum_commission=0),
        execution=BarExecution(slippage=FixedTicks(2), slippage_policy=policy),
    )
    assert result.cash[-1] == (9992 if policy == "cost" else 10000)
    assert len(result.fills) == (0 if policy == "strict" else 8)


@pytest.mark.parametrize("rebalance", [False, True])
def test_scheduled_weights_keep_fixed_shares_and_optional_rebalance(backend, rebalance):
    data = minute_data(volume=100000, symbols=("A", "B"), frequency="5min")
    targets = WeightTargets(
        sessions=data.timeline,
        weights={"A": [0.8] * 24 + [0.2] * 72, "B": [0.1] * 96},
        rebalance=rebalance,
    )
    compare(data, targets, backend)


def test_scheduled_rights_and_daily_taxes_are_not_skipped(backend):
    action = CorporateAction(
        action_id="bonus",
        symbol="A",
        kind="distribution",
        announced="2025-01-02",
        record_date="2025-01-02",
        ex_date="2025-01-03",
        pay_date="2025-01-06",
        share_credit_date="2025-01-03",
        share_listing_date="2025-01-06",
        cash_per_share=1,
        bonus_per_share=1,
        taxable_bonus_amount_per_share=0,
        source="synthetic scheduled dividend",
    )
    data = minute_data(days=3, volume=100000, actions=(action,))
    target = PositionTargets(sessions=data.timeline, quantities={"A": [100] * 250 + [0] * 470})
    result = compare(data, target, backend, costs=Costs(commission=0, minimum_commission=0))
    assert len(result.entitlements) == 1 and result.taxes
    assert result.holdings[240, 0] == 200 and result.holdings[-1, 0] == 0


def test_scheduled_retains_no_fill_reasons_auction_and_final_intention(backend):
    changes = {i: {"high": 10, "low": 10} for i in range(1, 200)}
    changes.update({i: {"phase": "auction"} for i in range(237, 240)})
    changes[239] = {"status": "suspended", "volume": 0}
    data = minute_data(changes=changes, volume=100)
    targets = PositionTargets(
        sessions=data.timeline,
        quantities={"A": [1000] * 238 + [2000] * 241 + [3000]},
    )
    result = compare(data, targets, backend, execution=BarExecution(slippage=FixedTicks(1)))
    assert any(o.reason == "suspended" for o in result.orders)
    assert result.intents[-1].status == "unexecuted"


def test_scheduled_cash_shortage_and_invalid_submission(backend):
    data = minute_data(
        volume=100000, rule_changes={"sell_minimum": 100, "allow_odd_lot_liquidation": False}
    )
    target = PositionTargets(sessions=data.timeline, quantities={"A": [1000] * 245 + [47] * 235})
    result = compare(data, target, backend, initial_cash=1005)
    assert any(o.reason == "insufficient_cash" for o in result.orders)
    assert any(o.status == "rejected" for o in result.orders)


def test_precomputed_subclass_still_runs_its_own_callback_every_bar(backend):
    seen = []

    class CustomTargets(PositionTargets):
        def __call__(self, ctx):
            seen.append(ctx.bar_index)
            super().__call__(ctx)

    data = minute_data(frequency="5min")
    targets = CustomTargets(sessions=data.timeline, quantities={"A": [0] * 96})
    result = Backtest(data).run(targets, backend=backend)
    assert seen == list(range(96))
    assert result.run_info.to_dict()["execution_path"] == "bar_callbacks"


def test_position_targets_snapshot_validation_and_provenance():
    data = minute_data()
    values = np.full(480, 100)
    targets = PositionTargets(sessions=data.timeline, quantities={"A": values})
    values[:] = 200
    result = Backtest(data).run(targets)
    assert result.holdings[-1, 0] == 100
    assert result.run_info.to_dict()["strategy"]["inputs"]["quantities"]["A"][0] == 100
    with pytest.raises(ValueError, match="quantity length"):
        PositionTargets(sessions=data.timeline, quantities={"A": [100]})
    with pytest.raises(ValueError, match="target quantity"):
        PositionTargets(sessions=data.timeline, quantities={"A": [0.5] * 480})
    with pytest.raises(ValueError, match="unknown securities"):
        Backtest(data).run(PositionTargets(sessions=data.timeline, quantities={"X": [0] * 480}))
    with pytest.raises(ValueError, match="exactly match"):
        Backtest(data).run(PositionTargets(sessions=data.sessions, quantities={"A": [0, 0]}))


def test_span_valuation_checks_int64_overflow_and_delisting():
    with pytest.raises(OverflowError, match="equity"):
        value_span(np.array([[10_000_000_000]]), np.array([1_000_000_000]), 0)
    with pytest.raises(ValueError, match="delisting"):
        value_span(np.array([[0]]), np.array([100]), 0)
    assert value_span(np.array([[10]]), np.array([100]), -1000).tolist() == [0]
    assert value_span(np.array([[0]]), np.array([0]), MAX_MONEY).tolist() == [MAX_MONEY]


def test_skipped_bars_still_value_each_price_and_cannot_see_future_targets(backend):
    changes = {i: {"close": f"{10 + (i % 5) / 100:.2f}"} for i in range(480)}
    data = minute_data(volume=100000, changes=changes)
    targets = PositionTargets(sessions=data.timeline, quantities={"A": [100] * 480})
    result = compare(data, targets, backend, costs=Costs(commission=0, minimum_commission=0))
    expected = 99000 + 100 * data.prices("close")[1:, 0]
    np.testing.assert_allclose(result.equity[1:], expected, rtol=0, atol=1e-9)
    changed = PositionTargets(sessions=data.timeline, quantities={"A": [100] * 300 + [300] * 180})
    future = Backtest(data, costs=Costs(commission=0, minimum_commission=0)).run(
        changed, backend=backend
    )
    np.testing.assert_array_equal(result.equity_units[:301], future.equity_units[:301])
    np.testing.assert_array_equal(result.holdings[:301], future.holdings[:301])
    assert future.holdings[301, 0] == 300
