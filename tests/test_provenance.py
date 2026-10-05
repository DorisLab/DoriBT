"""Parameters must actually drive execution, and metadata must explain its limits."""

from dataclasses import replace

import numpy as np
import pytest
from engine_fixtures import data_for

from doribt import Backtest, Costs, WeightTargets


def sized(ctx, *, quantity):
    ctx.target_positions({"A": quantity})


def test_recorded_parameters_drive_fills_and_are_snapshot_copies(backend):
    data = data_for([10, 10, 11])
    run = Backtest(data, costs=Costs(commission=".0002", minimum_commission=1, slippage_ticks=1))
    result = run.run(sized, parameters={"quantity": 100}, backend=backend)
    assert result.fills[0].quantity == 100
    info = result.run_info.to_dict()
    assert info["parameters"] == {"quantity": 100}
    assert info["costs"] == {
        "commission_ppm": 200,
        "minimum_commission_units": 10000,
        "slippage_ticks": 1,
    }
    assert info["initial_cash_units"] == 1_000_000_000
    assert info["data"]["fingerprint"] == data.fingerprint
    assert info["data"]["rules"][0]["source"] == "fictional"
    assert info["versions"]["numpy"] == np.__version__
    assert info["backend"] == backend
    assert ("numba" in info["versions"]) == (backend == "numba")
    assert len(info["engine_sha256"]) == 64
    assert len(info["strategy"]["source_sha256"]) == 64
    assert info["strategy"]["external_state"] == "not_captured"
    assert "code" not in info["strategy"]
    again = run.run(sized, parameters={"quantity": 100}, backend=backend)
    assert again.run_info == result.run_info
    info["parameters"]["quantity"] = 200
    assert result.run_info.to_dict()["parameters"] == {"quantity": 100}
    changed = run.run(sized, parameters={"quantity": 200}, backend=backend)
    assert changed.fills[0].quantity == 200
    assert changed.run_info.fingerprint != result.run_info.fingerprint
    changed_data = Backtest(replace(data, source="different source")).run(
        sized, parameters={"quantity": 100}
    )
    assert changed_data.data_fingerprint != result.data_fingerprint


def test_nested_parameters_not_mutated_in_caller_and_initial_values_recorded():
    parameters = {"state": {"quantity": 100}}

    def callback(ctx, *, state):
        ctx.target_positions({"A": state["quantity"]})
        state["quantity"] += 100

    result = Backtest(data_for([10, 10, 10])).run(callback, parameters=parameters)
    assert [f.quantity for f in result.fills] == [100, 100]
    assert parameters == {"state": {"quantity": 100}}
    assert result.run_info.to_dict()["parameters"] == parameters


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"quantity": 100, "bad": 1},
        {1: 10},
        {"quantity": float("nan")},
        {"quantity": (100,)},
        {"quantity": {1: 100}},
    ],
)
def test_bad_parameters_fail_before_first_strategy_call(parameters):
    with pytest.raises(ValueError):
        Backtest(data_for([10] * 3)).run(sized, parameters=parameters)


def test_precomputed_targets_keep_exact_inputs_and_reject_extra_parameters():
    data = data_for([10] * 3)
    target = WeightTargets(sessions=data.sessions, weights={"A": [0.5, 0, 0]})
    result = Backtest(data).run(target)
    strategy = result.run_info.to_dict()["strategy"]
    assert strategy["kind"] == "weight_targets"
    assert strategy["inputs"]["weights"] == {"A": [0.5, 0, 0]}
    assert len(strategy["input_sha256"]) == 64
    with pytest.raises(ValueError, match="supplied parameters"):
        Backtest(data).run(target, parameters={"unexpected": 1})


def test_interactive_function_source_unavailable_is_not_claimed_as_captured():
    scope = {}
    exec("def callback(ctx):\n    pass", scope)
    info = Backtest(data_for([10])).run(scope["callback"]).run_info.to_dict()
    assert info["strategy"]["source_sha256"] is None
