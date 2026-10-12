"""权重编译循环对照完整逐 bar 回调，保留记录、定量时点与错误链。"""

from unittest.mock import patch

import numpy as np
import pytest
from engine_fixtures import data_for
from minute_fixtures import minute_data
from test_compiled_fastpath_review import assert_review_parity

from doribt import Backtest, BarExecution, Costs, WeightTargets


@pytest.mark.numba
@pytest.mark.parametrize("minute", [False, True])
@pytest.mark.parametrize("sizing", ["close", "execution"])
@pytest.mark.parametrize("rebalance", [False, True])
def test_weight_schedule_preserves_all_output_fields(minute, sizing, rebalance):
    data = (
        minute_data(frequency="5min", symbols=("A", "B"), volume=150, settlement=1)
        if minute
        else data_for([10, 10, 11, 9, 12], [11, 10, 10, 12, 13])
    )
    count = len(data.timeline)
    first = np.where(np.arange(count) % 7 < 3, 0.3, 0.6)
    second = np.where(np.arange(count) % 11 < 5, 0.2, 0.4)
    targets = WeightTargets(
        sessions=data.timeline,
        weights={"B": second, "A": first},
        sizing=sizing,
        rebalance=rebalance,
    )
    test = Backtest(
        data,
        initial_cash=10000,
        costs=Costs(commission=".0003", minimum_commission=5),
        execution=BarExecution(participation=".5"),
    )
    actual = test.run(targets, backend="numba")
    reference = test.run(lambda ctx: targets(ctx), backend="numba")
    assert_review_parity(actual, reference)
    with patch("doribt.runtime.compiled_schedule.eligible", return_value=False):
        fallback = test.run(targets, backend="numba")
    assert_review_parity(actual, fallback)
    assert actual.run_info == fallback.run_info


@pytest.mark.numba
@pytest.mark.parametrize("sizing", ["close", "execution"])
def test_weight_sizing_overflow_preserves_original_error_and_timing(sizing):
    data = data_for([1, 1, 1])
    targets = WeightTargets(sessions=data.timeline, weights={"A": [1, 1, 1]}, sizing=sizing)
    test = Backtest(
        data,
        initial_cash=2_000_000_000,
        costs=Costs(commission=0, minimum_commission=0),
        execution=BarExecution(),
    )
    with pytest.raises((RuntimeError, OverflowError)) as actual:
        test.run(targets, backend="numba")
    with pytest.raises((RuntimeError, OverflowError)) as reference:
        test.run(lambda ctx: targets(ctx), backend="numba")
    assert type(actual.value) is type(reference.value)
    assert str(actual.value) == str(reference.value)
    assert type(actual.value.__cause__) is type(reference.value.__cause__)
    assert str(actual.value.__cause__) == str(reference.value.__cause__)
