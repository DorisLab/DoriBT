"""非活动规则区间的权重目标保留原语义并进入完整编译。"""

import pytest
from engine_fixtures import data_for
from minute_fixtures import minute_data
from test_compiled_fastpath_review import assert_review_parity

from doribt import Backtest, BarExecution, Costs, WeightTargets


def inactive_weight_case(backend, sizing="close", rebalance=False):
    inactive = dict(
        status="unlisted",
        open=None,
        high=None,
        low=None,
        close=None,
        volume=0,
        upper_limit=None,
        lower_limit=None,
    )
    data = minute_data(
        days=2,
        frequency="5min",
        symbols=("A", "B"),
        changes={index * 2: inactive for index in range(10)},
        volume=100000,
    )
    target = WeightTargets(
        sessions=data.timeline,
        weights={"A": [0] * 12 + [0.5] * 84, "B": [0.5] * 96},
        sizing=sizing,
        rebalance=rebalance,
    )
    test = Backtest(
        data,
        initial_cash=10000,
        costs=Costs(commission=0, minimum_commission=0),
        execution=BarExecution(),
    )
    result = test.run(target, backend=backend)
    reference = test.run(lambda ctx: target(ctx), backend=backend)
    assert_review_parity(result, reference)
    assert result.holdings[-1].tolist() == [500, 500]
    return result, ()


@pytest.mark.numba
@pytest.mark.parametrize("sizing", ["close", "execution"])
@pytest.mark.parametrize("rebalance", [False, True])
def test_inactive_weight_rows_enter_compiled_schedule(monkeypatch, sizing, rebalance):
    from doribt.runtime import compiled_schedule

    execute = compiled_schedule.execute
    calls = []

    def observed(*args):
        calls.append(True)
        return execute(*args)

    monkeypatch.setattr(compiled_schedule, "execute", observed)
    result, _ = inactive_weight_case("numba", sizing, rebalance)
    assert calls == [True]
    assert result.run_info.to_dict()["execution_plan"]["plan"] == "compiled_targets"


def full_cash_weight_case(backend, sizing, rebalance, minute):
    data = (
        minute_data(days=3, frequency="5min", symbols=("A", "B"), volume=337, settlement=1)
        if minute
        else data_for([10, 9, 11, 8, 10], [11, 12, 8, 13, 9])
    )
    count = len(data.timeline)
    weights = {
        "B": [0.333333 if i % 5 < 2 else 0.666667 for i in range(count)],
        "A": [0.666667 if i % 5 < 2 else 0.333333 for i in range(count)],
    }
    targets = WeightTargets(
        sessions=data.timeline, weights=weights, sizing=sizing, rebalance=rebalance
    )
    test = Backtest(
        data,
        initial_cash=10000,
        costs=Costs(commission=".0003", minimum_commission=5),
        execution=BarExecution(participation=".17"),
    )
    result = test.run(targets, backend=backend)
    reference = test.run(lambda ctx: targets(ctx), backend=backend)
    assert_review_parity(result, reference)
    assert result.cash_units.min() >= 0
    return result, ()


def final_unsized_case(backend):
    data = data_for([10])
    target = WeightTargets(sessions=data.timeline, weights={"A": [1]}, sizing="execution")
    test = Backtest(data, execution=BarExecution())
    result = test.run(target, backend=backend)
    reference = test.run(lambda ctx: target(ctx), backend=backend)
    assert_review_parity(result, reference)
    assert not result.orders and not result.fills
    assert result.intents[0].quantity is None
    assert result.intents[0].sized_at is None
    assert result.intents[0].status == "unexecuted"
    return result, ()


WEIGHT_CASES = {
    f"full_cash_weight_{sizing}_{rebalance}_{minute}": (
        lambda backend, sizing=sizing, rebalance=rebalance, minute=minute: full_cash_weight_case(
            backend, sizing, rebalance, minute
        )
    )
    for sizing in ("close", "execution")
    for rebalance in (False, True)
    for minute in (False, True)
}
WEIGHT_CASES["final_unsized_weight"] = final_unsized_case


@pytest.mark.parametrize("sizing", ["close", "execution"])
def test_unlisted_nonzero_weight_keeps_error_chain(backend, sizing):
    inactive = dict(status="unlisted", open=None, high=None, low=None, close=None, volume=0)
    data = data_for([10] * 3, changes={0: inactive, 1: inactive})
    target = WeightTargets(sessions=data.timeline, weights={"A": [1] * 3}, sizing=sizing)
    test = Backtest(data, execution=BarExecution())
    errors = []
    for strategy in (target, lambda ctx: target(ctx)):
        with pytest.raises((RuntimeError, ValueError)) as caught:
            test.run(strategy, backend=backend)
        errors.append(
            (
                type(caught.value),
                str(caught.value),
                type(caught.value.__cause__),
                str(caught.value.__cause__),
            )
        )
    assert errors[0] == errors[1]
    assert "current valuation" in errors[0][1]
