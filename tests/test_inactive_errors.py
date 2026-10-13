"""E01—E05：规则查找、估值与定量错误保持发生顺序和原子性。"""

from dataclasses import replace

import numpy as np
import pytest
from inactive_fixtures import scenario

from doribt import Backtest, BarExecution, WeightTargets
from doribt.kernels.compiled import compile_data
from doribt.kernels.scheduled_weights import replace_weights


def failure(test, target, backend):
    with pytest.raises((ValueError, RuntimeError, OverflowError)) as caught:
        test.run(target, backend=backend)
    error = caught.value
    return type(error).__name__, str(error), type(error.__cause__).__name__, str(error.__cause__)


@pytest.mark.numba
@pytest.mark.parametrize("sizing", ["close", "execution"])
@pytest.mark.parametrize("full_rules", [False, True])
@pytest.mark.parametrize("name", ["never", "pending_delisted", "delisted"])
def test_error_stage_and_chain(name, sizing, full_rules):
    data, _ = scenario(name, full_rules=full_rules)
    target = WeightTargets(
        sessions=data.timeline,
        weights={"A": [0.5] * 8, "B": [0.5] * 8},
        sizing=sizing,
        rebalance=name == "pending_delisted",
    )
    test = Backtest(data, initial_cash=10_000, execution=BarExecution())
    reference = failure(test, lambda ctx: target(ctx), "python")
    assert failure(test, target, "python") == reference
    assert failure(test, target, "numba") == reference
    expected = (
        "held security"
        if name == "delisted"
        else ("current valuation" if full_rules else "missing historical rule")
    )
    assert expected in reference[1]


@pytest.mark.numba
def test_future_illegal_weight_does_not_preempt_earlier_valuation_error():
    data, _ = scenario("delisted")
    target = WeightTargets(sessions=data.timeline, weights={"A": [0.5] * 7 + [1]}, rebalance=True)
    test = Backtest(data, execution=BarExecution())
    reference = failure(test, lambda ctx: target(ctx), "python")
    assert "held security" in reference[1]
    assert failure(test, target, "numba") == reference


def test_close_sizing_finishes_all_symbols_before_replacing_intents():
    data, _ = scenario("never", full_rules=False)
    # 让 A 正常、B 未上市，第二个证券失败时不能撤销第一个证券的旧意图。
    rules = compile_data(data).sizing_rules[:, ::-1].copy()
    closes = compile_data(data).closes[:, ::-1].copy()
    weights = np.full((8, 2), 500_000, dtype=np.int64)
    positions = np.zeros(2, dtype=np.int64)
    active = np.array([0, 1], dtype=np.int64)
    intents = np.zeros((8, 9), dtype=np.int64)
    children = np.array([0, 1], dtype=np.int64)
    orders = np.ones((8, 24), dtype=np.int64)
    frozen = np.array([20_000], dtype=np.int64)
    shares = np.array([10, 20], dtype=np.int64)
    watched = (active, intents, children, orders, frozen, shares)
    original = [array.copy() for array in watched]
    with pytest.raises(ValueError) as caught:
        replace_weights(
            0,
            weights,
            1,
            True,
            100_000_000,
            closes,
            rules,
            positions,
            active,
            intents,
            2,
            children,
            orders,
            frozen,
            shares,
        )
    assert caught.value.args == ("weight_sizing", 0, 1, 3, 1)
    for left, right in zip(watched, original, strict=True):
        np.testing.assert_array_equal(left, right)


@pytest.mark.parametrize("change", ["missing_rule", "missing_row", "duplicate", "bad_transition"])
def test_invalid_data_still_fails_before_execution(change):
    data, _ = scenario("listing")
    with pytest.raises(ValueError):
        if change == "missing_rule":
            replace(data, rules=replace(data.rules, periods=()))
        elif change == "missing_row":
            replace(data, bars=data.bars[1:])
        elif change == "duplicate":
            replace(data, bars=(*data.bars, data.bars[0]))
        else:
            inactive = data.bars[0]
            bars = (*data.bars[:12], replace(inactive, session=data.sessions[6]), *data.bars[13:])
            replace(data, bars=bars)
