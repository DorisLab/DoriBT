"""路径审计必须来自已选择的执行器，并可原样导出。"""

import json
import os
import subprocess
import sys

import pytest
from corporate_fixtures import distribution, market_with_actions
from engine_fixtures import data_for

from doribt import Backtest, BarExecution, PositionTargets, WeightTargets


def audit(data, strategy, backend):
    return (
        Backtest(data, execution=BarExecution()).run(strategy, backend=backend).run_info.to_dict()
    )


def test_python_and_callback_plans(backend, tmp_path):
    data = data_for([10] * 3)
    target = WeightTargets(sessions=data.timeline, weights={"A": [0.5] * 3})
    result = Backtest(data, execution=BarExecution()).run(target, backend=backend)
    info = result.run_info.to_dict()
    assert info["execution_path"] == "scheduled_segments"
    plan = info["execution_plan"]
    assert plan["requested_backend"] == plan["actual_backend"] == backend
    assert plan["plan"] == ("compiled_targets" if backend == "numba" else "scheduled_segments")
    callback = audit(data, lambda ctx: target(ctx), backend)["execution_plan"]
    assert callback["plan"] == "bar_callbacks"
    assert any(reason["code"] == "callback" for reason in callback["fallback_reasons"])
    folder = tmp_path / "export"
    result.export(folder)
    assert json.loads((folder / "run.json").read_text(encoding="utf-8"))["execution_plan"] == plan


@pytest.mark.numba
def test_corporate_actions_and_custom_targets_explain_fallback():
    data = market_with_actions([10] * 5, [distribution()])
    target = WeightTargets(sessions=data.timeline, weights={"A": [0.5] * 5})
    plan = audit(data, target, "numba")["execution_plan"]
    assert plan["plan"] == "scheduled_segments"
    assert plan["compiled_scope"] == "matching"
    assert plan["fallback_reasons"][0]["code"] == "corporate_actions"

    class Custom(WeightTargets):
        pass

    data = data_for([10] * 3)
    custom = Custom(sessions=data.timeline, weights={"A": [0.5] * 3})
    plan = audit(data, custom, "numba")["execution_plan"]
    assert plan["plan"] == "bar_callbacks"
    assert plan["fallback_reasons"][0]["code"] == "custom_target"


@pytest.mark.numba
def test_disabled_jit_is_never_reported_as_compiled():
    program = """
from engine_fixtures import data_for
from doribt import Backtest, BarExecution, WeightTargets
d = data_for([10] * 3)
t = WeightTargets(sessions=d.timeline, weights={'A': [.5] * 3})
r = Backtest(d, execution=BarExecution()).run(t, backend='numba')
p = r.run_info.to_dict()['execution_plan']
assert p['requested_backend'] == 'numba' and p['actual_backend'] == 'python'
assert not p['jit_enabled'] and p['compiled_scope'] == 'none'
assert p['plan'] == 'scheduled_segments'
assert p['fallback_reasons'][0]['code'] == 'jit_disabled'
"""
    subprocess.run(
        [sys.executable, "-c", program],
        check=True,
        env=os.environ | {"NUMBA_DISABLE_JIT": "1", "PYTHONPATH": "tests"},
    )


@pytest.mark.numba
def test_daily_position_targets_remain_compiled():
    data = data_for([10] * 3)
    targets = PositionTargets(sessions=data.timeline, quantities={"A": [100, 0, 0]})
    plan = audit(data, targets, "numba")["execution_plan"]
    assert plan["plan"] == "compiled_targets" and not plan["fallback_reasons"]
