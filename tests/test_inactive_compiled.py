"""C01—C12：完整记录、手算结果及 0.6.1 冻结证据共同约束编译扩展。"""

import json
from pathlib import Path

import numpy as np
import pytest
from inactive_fixtures import CASES, ledger, scenario

from doribt import Backtest, BarExecution, Costs, FixedBps, FixedTicks, VolumeImpact
from doribt.serialization import encode


@pytest.mark.numba
@pytest.mark.parametrize(
    "name,rebalance",
    [
        (name, rebalance)
        for name in CASES
        for rebalance in (False, True)
        if name != "pending_delisted" or not rebalance
    ],
)
@pytest.mark.parametrize("full_rules", [False, True])
@pytest.mark.parametrize("sizing", ["close", "execution"])
def test_lifecycle_ledger(name, full_rules, sizing, rebalance):
    data, target = scenario(name, sizing, rebalance, full_rules)
    test = Backtest(data, initial_cash=10_000, execution=BarExecution(participation=".17"))
    reference = test.run(lambda ctx: target(ctx), backend="python")
    prepared = test.run(target, backend="python")
    compiled = test.run(target, backend="numba")
    assert encode(ledger(compiled)) == encode(ledger(reference)) == encode(ledger(prepared))
    plan = compiled.run_info.to_dict()["execution_plan"]
    assert plan["plan"] == "compiled_targets" and plan["jit_enabled"]
    assert plan["fallback_reasons"] == []
    if name in ("never", "omitted"):
        assert not any(fill.symbol == "A" for fill in compiled.fills)
    if name == "pending_delisted":
        pending = [intent for intent in compiled.intents if intent.symbol == "A"]
        assert pending[-1].quantity == 500 and pending[-1].status == "unexecuted"


@pytest.mark.numba
@pytest.mark.parametrize("model", [FixedBps(5), FixedTicks(1), VolumeImpact(".01")])
@pytest.mark.parametrize("policy", ["strict", "cap", "cost"])
def test_shared_cash_slippage(model, policy):
    data, target = scenario("cash")
    test = Backtest(
        data,
        initial_cash=1000,
        costs=Costs(commission=".003", minimum_commission=5),
        execution=BarExecution(participation=".3", slippage=model, slippage_policy=policy),
    )
    reference = test.run(lambda ctx: target(ctx))
    compiled = test.run(target, backend="numba")
    assert encode(ledger(reference)) == encode(ledger(compiled))


@pytest.mark.parametrize("sizing", ["close", "execution"])
@pytest.mark.parametrize("rebalance", [False, True])
def test_six_days_hand_calculation(backend, sizing, rebalance):
    import importlib.util

    path = Path(__file__).parents[1] / "examples/inactive_weights.py"
    spec = importlib.util.spec_from_file_location("inactive_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = module.make_data()
    from doribt import WeightTargets

    target = WeightTargets(
        sessions=data.timeline,
        weights={"A": [0, 0, 0.5, 0.5, 0, 0], "B": [0.5] * 6},
        sizing=sizing,
        rebalance=rebalance,
    )
    result = Backtest(
        data,
        initial_cash=10_000,
        costs=Costs(commission=0, minimum_commission=0),
        execution=BarExecution(),
    ).run(target, backend=backend)
    assert [(f.symbol, f.quantity, f.session) for f in result.fills] == [
        ("B", 500, data.sessions[1]),
        ("A", 500, data.sessions[3]),
        ("A", -500, data.sessions[5]),
    ]
    np.testing.assert_array_equal(result.equity, [10_000] * 6)
    assert result.holdings[-1].tolist() == [0, 500]


def test_frozen_061_ledgers(backend):
    frozen = json.loads((Path(__file__).parent / "fixtures/inactive-061.json").read_text())
    for case in frozen["cases"]:
        data, target = scenario(**case["inputs"])
        result = Backtest(
            data, initial_cash=10_000, execution=BarExecution(participation=".17")
        ).run(target, backend=backend)
        assert json.loads(encode(ledger(result))) == case["ledger"], case["inputs"]
