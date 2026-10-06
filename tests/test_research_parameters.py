import json

import pytest
from engine_fixtures import data_for
from minute_fixtures import minute_data

from doribt import Backtest, BarExecution, Costs, FixedBps, Parameter, ParameterSet, RunConfig


def test_declared_defaults_and_overrides_drive_real_orders_and_snapshot(backend):
    declarations = {
        "quantity": Parameter(
            type="int", default=100, minimum=100, maximum=500, step=100, label="持仓", unit="shares"
        )
    }
    schema = ParameterSet(declarations)
    declarations.clear()
    data = data_for([10] * 3)
    engine = Backtest(
        data, config=RunConfig(backend=backend, costs=Costs(commission=0, minimum_commission=1))
    )

    def strategy(ctx, *, quantity):
        ctx.target_positions({"A": quantity})

    first = engine.run(strategy, parameter_schema=schema)
    second = engine.run(strategy, parameter_schema=schema, parameters={"quantity": 200})
    assert first.fills[0].quantity == 100 and second.fills[0].quantity == 200
    info = first.run_info.to_dict()
    assert info["parameters"] == {"quantity": 100}
    assert info["parameter_schema"]["properties"]["quantity"]["unit"] == "shares"
    assert info["config"]["minimum_commission"] == 1
    assert info["backend"] == backend
    assert info["model"] == "bar-partial-next-open-v1"


@pytest.mark.parametrize("value", [True, 100.0, 99, 501, 150, None, float("nan")])
def test_invalid_parameters_fail_before_callback(value):
    schema = ParameterSet(
        {"quantity": Parameter(type="int", default=100, minimum=100, maximum=500, step=100)}
    )
    calls = []
    with pytest.raises(ValueError, match="parameter quantity"):
        Backtest(data_for([10] * 3)).run(
            lambda ctx, **kw: calls.append(ctx),
            parameters={"quantity": value},
            parameter_schema=schema,
        )
    assert calls == []


def test_schema_unknown_keys_choices_and_decimal_steps():
    schema = ParameterSet(
        {
            "weight": Parameter(type="float", default=0.3, minimum=0.1, step=0.1),
            "mode": Parameter(type="str", default="fast", choices=("fast", "slow")),
        }
    )
    assert schema.resolve()["weight"] == 0.3
    with pytest.raises(ValueError, match="unknown parameters"):
        schema.resolve({"typo": 10})
    with pytest.raises(ValueError, match="choice"):
        schema.resolve({"mode": "unknown"})
    with pytest.raises(ValueError):
        Parameter(type="float", default=0, minimum=2, maximum=1)
    with pytest.raises(ValueError):
        Parameter(type="str", default="x", step=1)
    with pytest.raises(ValueError):
        ParameterSet({"class": Parameter(type="int", default=1)})


@pytest.mark.parametrize(
    "commission,minimum,expected", [(0, 0, 0), (0.001, 0, 2), (0, 7, 7), (0.001, 7, 7)]
)
def test_configurable_commission_and_minimum_apply_once_per_partially_filled_order(
    backend, commission, minimum, expected
):
    data = minute_data(days=1, frequency="5min")
    config = RunConfig.from_dict(
        {"commission": commission, "minimum_commission": minimum, "backend": backend}
    )
    result = Backtest(data, config=config).run(
        lambda ctx: ctx.order("A", 200, valid_for="day") if ctx.bar_index == 0 else None
    )
    assert len(result.fills) == 4
    assert sum(fill.commission for fill in result.fills) == expected
    assert result.cash[-1] == 100_000 - 2000 - expected
    assert result.run_info.to_dict()["config"]["commission"] == commission


def test_runtime_config_round_trip_and_conflicts():
    original = RunConfig(
        costs=Costs(commission=".0001", minimum_commission=0),
        execution=BarExecution(participation=0.1, slippage=FixedBps(5)),
    )
    rebuilt = RunConfig.from_dict(json.loads(json.dumps(original.to_dict())))
    assert rebuilt.to_dict() == original.to_dict()
    for values in (
        {"minimum_commission": -1},
        {"commission": 2},
        {"minimum_commission": 0.001},
        {"slippage_value": 0.5},
        {"backend": "gpu"},
        {"margin": 0.5},
    ):
        with pytest.raises(ValueError):
            RunConfig.from_dict(values)
    with pytest.raises(ValueError, match="cannot be combined"):
        Backtest(data_for([10]), config=original, initial_cash=100)
    with pytest.raises(ValueError, match="slippage"):
        RunConfig(costs=Costs(slippage_ticks=1))
    with pytest.raises(ValueError):
        Backtest(data_for([10])).run(lambda ctx: None, backend="")


def test_reusing_backtest_with_changed_fees_records_effective_configuration():
    engine = Backtest(data_for([10, 10]), config=RunConfig())
    before = engine.run(lambda ctx: ctx.target_positions({"A": 100}))
    engine.costs = Costs(commission=0.001, minimum_commission=0)
    after = engine.run(lambda ctx: ctx.target_positions({"A": 100}))
    assert before.fills[0].commission == 5
    assert after.fills[0].commission == 1
    assert after.run_info.to_dict()["config"]["minimum_commission"] == 0
    assert after.run_info.to_dict()["config"]["commission"] == 0.001
