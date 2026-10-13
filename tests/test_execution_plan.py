"""预计算编译路径不应构造未使用的回调账户或完整历史窗口。"""

from unittest.mock import patch

import pytest
from engine_fixtures import data_for
from minute_fixtures import minute_data
from test_compiled_fastpath_review import assert_review_parity

from doribt import Backtest, BarExecution, Costs, PositionTargets, WeightTargets
from doribt.kernels.compiled import prepare
from doribt.runtime.execution_plan import target_run

pytestmark = pytest.mark.numba


@pytest.mark.parametrize("minute", [False, True])
@pytest.mark.parametrize("weighted", [False, True])
def test_compiled_targets_avoid_callback_state_and_history(minute, weighted):
    data = minute_data(days=1, volume=100_000) if minute else data_for([10, 11, 12])
    count = len(data.timeline)
    target = (
        WeightTargets(sessions=data.timeline, weights={"A": [0.1] * count})
        if weighted
        else PositionTargets(sessions=data.timeline, quantities={"A": [100] * count})
    )
    test = Backtest(data, costs=Costs(commission=0, minimum_commission=0), execution=BarExecution())
    prepared = prepare(data)
    test._prepared = prepared
    with (
        patch("doribt.runtime.engine._Run.__init__", side_effect=AssertionError("unused run")),
        patch(
            "doribt.accounting.account.Account.__init__",
            side_effect=AssertionError("unused account"),
        ),
        patch.object(type(data), "prices", side_effect=AssertionError("unused OHLC history")),
    ):
        actual = test.run(target, backend="numba")
    reference = test.run(lambda ctx: target(ctx), backend="numba")
    assert_review_parity(actual, reference)
    assert actual.holdings[-1, 0] > 0


def test_plan_is_chosen_once_before_run_allocation():
    data = data_for([10, 11, 12])
    prepared = prepare(data)
    target = PositionTargets(sessions=data.timeline, quantities={"A": [100, 100, 100]})
    with (
        patch("doribt.runtime.compiled_schedule.eligible", return_value=False) as schedule,
        patch("doribt.runtime.compiled_targets.eligible", return_value=True) as daily,
        patch("doribt.runtime.engine._Run.__init__", side_effect=AssertionError("unused run")),
    ):
        run = target_run(prepared, 1_000_000_000, Costs(), "numba", BarExecution(), target)
        assert run.plan == "daily_targets"
        schedule.assert_called_once()
        daily.assert_called_once()


def test_prepared_history_remains_lazy_across_independent_accounts():
    data = data_for([10, 11, 12])
    prepared = prepare(data)
    target = PositionTargets(sessions=data.timeline, quantities={"A": [100, 100, 100]})
    test = Backtest(data, execution=BarExecution())
    test._prepared = prepared
    with patch.object(type(data), "prices", side_effect=AssertionError("unused OHLC history")):
        first = test.run(target, backend="numba")
        second = test.run(target, backend="numba")
    assert_review_parity(first, second)
    assert first.holdings is not second.holdings
    assert not first.holdings.flags.writeable
