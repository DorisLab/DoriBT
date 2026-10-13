"""独立复核：每日目标路径须保留逐 bar 账本与失败语义。"""

from dataclasses import fields
from datetime import date, timedelta
from unittest.mock import patch

import numpy as np
import pytest
from corporate_fixtures import distribution, market_with_actions
from engine_fixtures import data_for
from minute_fixtures import minute_data

from doribt import (
    Backtest,
    BarExecution,
    Costs,
    FixedBps,
    FixedTicks,
    Instrument,
    MarketData,
    PositionTargets,
    RuleBook,
    RulePeriod,
    TradingRule,
    VolumeImpact,
    WeightTargets,
)


def assert_review_parity(actual, reference):
    for item in fields(actual):
        if item.name == "run_info":
            continue
        left, right = getattr(actual, item.name), getattr(reference, item.name)
        if isinstance(left, np.ndarray):
            np.testing.assert_array_equal(left, right, err_msg=item.name)
            assert left.dtype == right.dtype
            assert left.flags.writeable == right.flags.writeable
        else:
            assert left == right, item.name
    left, right = actual.run_info.to_dict(), reference.run_info.to_dict()
    for key in ("strategy", "execution_path", "execution_plan"):
        left.pop(key, None)
        right.pop(key, None)
    assert left == right


def compare_review(data, quantities, backend, **kwargs):
    targets = PositionTargets(sessions=data.timeline, quantities=quantities)
    test = Backtest(data, **kwargs)
    actual = test.run(targets, backend=backend)
    reference = test.run(lambda ctx: targets(ctx), backend=backend)
    assert_review_parity(actual, reference)
    with (
        patch("doribt.runtime.compiled_targets.eligible", return_value=False),
        patch("doribt.runtime.compiled_schedule.eligible", return_value=False),
    ):
        fallback = test.run(targets, backend=backend)
    assert_review_parity(actual, fallback)
    assert fallback.run_info.to_dict()["execution_plan"]["plan"] == "scheduled_segments"
    if backend == "numba":
        from doribt.kernels.scheduled_loop import simulate_schedule
        from doribt.kernels.target_loop import simulate_targets

        with (
            patch(
                "doribt.runtime.compiled_targets.compiled_targets", return_value=simulate_targets
            ),
            patch(
                "doribt.runtime.compiled_schedule.compiled_schedule", return_value=simulate_schedule
            ),
        ):
            interpreted = test.run(targets, backend=backend)
        assert_review_parity(actual, interpreted)
        assert actual.run_info == interpreted.run_info
    return actual


def review_daily_case(seed):
    rng = np.random.default_rng(seed)
    calendar = tuple(date(2025, 1, 2) + timedelta(days=i) for i in range(16))
    symbols = ("A", "B", "C")
    periods, rows = [], []
    for column, symbol in enumerate(symbols):
        for start, end, settlement in ((0, 7, seed % 3), (8, 15, (seed + 1) % 3)):
            rule = TradingRule(
                price_tick=".01",
                buy_minimum=100,
                buy_step=100 if column != 1 else 1,
                sell_minimum=100 if seed % 2 else 1,
                sell_step=100 if column != 2 else 1,
                allow_odd_lot_liquidation=bool(seed % 2),
                order_maximum=500,
                settlement_days=settlement,
                stamp_duty_sell=".0005",
                transfer_fee=".00001",
            )
            periods.append(
                RulePeriod(
                    symbol=symbol,
                    start=calendar[start],
                    end=calendar[end],
                    rule=rule,
                    source="独立差分测试",
                    version="1",
                )
            )
    for session in calendar:
        for symbol in symbols:
            suspended = rng.random() < 0.08
            rows.append(
                dict(
                    session=session,
                    symbol=symbol,
                    status="suspended" if suspended else "trading",
                    open=int(rng.integers(5, 21)),
                    close=int(rng.integers(5, 21)),
                    high=25,
                    low=1,
                    volume=0 if suspended else int(rng.choice([0, 101, 777, 10000])),
                    upper_limit=None,
                    lower_limit=None,
                )
            )
    data = MarketData.from_records(
        rows,
        calendar=calendar,
        instruments=[Instrument(symbol=s, kind="stock") for s in symbols],
        rules=RuleBook(tuple(periods)),
        source="独立随机化目标回测",
    )
    quantities = {
        symbol: rng.choice([0, 47, 99, 100, 200, 333, 800], size=16).tolist()
        for symbol in reversed(symbols)
    }
    return data, quantities


@pytest.mark.parametrize("seed", range(18))
def test_review_daily_randomized_complete_result(backend, seed):
    data, quantities = review_daily_case(seed)
    models = (FixedTicks(1), FixedBps(7), VolumeImpact(".2"))
    compare_review(
        data,
        quantities,
        backend,
        initial_cash=1000 if seed % 2 else 10000,
        costs=Costs(commission=".0003", minimum_commission=5 if seed % 3 else 200),
        execution=BarExecution(
            participation=(".01", ".17", 1)[seed % 3],
            slippage=models[seed % 3],
            slippage_policy=("strict", "cap", "cost")[seed % 3],
        ),
    )


def test_review_pending_priority_differs_from_symbol_order(backend):
    data = data_for([10] * 5, [10] * 5, settlement=0)
    result = compare_review(
        data,
        {"B": [100, 200, 200, 0, 0], "A": [100, 100, 200, 200, 200]},
        backend,
        initial_cash=1500,
        costs=Costs(commission=0, minimum_commission=0),
        execution=BarExecution(),
    )
    assert result.holdings[1].tolist() == [50, 100]
    assert result.fills[0].symbol == "B"


def test_review_remaining_tax_lots_keep_original_ids(backend):
    data = data_for([10] * 5, settlement=0)
    result = compare_review(
        data,
        {"A": [100, 200, 0, 100, 100]},
        backend,
        initial_cash=10000,
        costs=Costs(commission=0, minimum_commission=0),
        execution=BarExecution(),
    )
    assert len(result.tax_lots) == 1
    assert result.tax_lots[0].lot_id == 3
    assert result.tax_lots[0].quantity == 100
    assert result.cash[-1] == 9000


def test_review_minute_schedule_preserves_day_net_tax_lots(backend):
    data = minute_data(frequency="5min", days=2, settlement=0, volume=100000)
    compare_review(
        data,
        {"A": [100] * 12 + [0] * 12 + [200] * 24 + [0] * 48},
        backend,
        costs=Costs(commission=".0003", minimum_commission=5),
        execution=BarExecution(participation=".1"),
    )


@pytest.mark.parametrize("quantities", [{}, {"A": [0] * 5}, {"A": [47] * 5}])
def test_review_empty_and_below_minimum_targets(backend, quantities):
    compare_review(data_for([10] * 5), quantities, backend, execution=BarExecution())


def test_review_final_close_only_intent(backend):
    result = compare_review(data_for([10]), {"A": [100]}, backend, execution=BarExecution())
    assert not result.orders
    assert result.intents[0].status == "unexecuted"


def test_review_inactive_listing_transition(backend):
    empty = dict(status="unlisted", open=None, high=None, low=None, close=None, volume=0)
    data = data_for([10] * 5, changes={0: empty, 1: empty})
    result = compare_review(data, {"A": [100] * 5}, backend, execution=BarExecution())
    assert result.holdings[:, 0].tolist() == [0, 0, 0, 100, 100]


@pytest.mark.parametrize("case", ["reservation", "equity", "delisting"])
def test_review_overflow_and_delisting_fail_identically(backend, case):
    changes, cash, quantity = None, 10000, 100
    prices = [10, 10, 10]
    if case == "reservation":
        prices, quantity = [1000000] * 3, 1000000000
    elif case == "equity":
        prices, cash = [10, 10, 1000000], 10000000000
    else:
        changes = {2: dict(status="delisted", open=None, high=None, low=None, close=None, volume=0)}
    data = data_for(prices, changes=changes)
    targets = PositionTargets(sessions=data.timeline, quantities={"A": [quantity] * 3})
    test = Backtest(
        data,
        initial_cash=cash,
        execution=BarExecution(),
        costs=Costs(commission=0, minimum_commission=0),
    )
    error_type = ValueError if case == "delisting" else OverflowError
    with pytest.raises(error_type) as reference:
        test.run(lambda ctx: targets(ctx), backend=backend)
    with pytest.raises(error_type) as actual:
        test.run(targets, backend=backend)
    assert str(actual.value) == str(reference.value)
    if backend == "numba":
        from doribt.kernels.target_loop import simulate_targets

        with patch(
            "doribt.runtime.compiled_targets.compiled_targets", return_value=simulate_targets
        ):
            with pytest.raises(error_type) as interpreted:
                test.run(targets, backend=backend)
        assert str(interpreted.value) == str(reference.value)


@pytest.mark.parametrize("volume,expected", [(0, [50, 0]), (60, [50, 60])])
def test_review_blocked_or_partial_buy_keeps_reservation(backend, volume, expected):
    data = data_for([10] * 3, [10] * 3, settlement=0, changes={3: {"volume": volume}})
    result = compare_review(
        data,
        {"B": [100] * 3, "A": [100] * 3},
        backend,
        initial_cash=1500,
        costs=Costs(commission=0, minimum_commission=0),
        execution=BarExecution(participation=1),
    )
    assert result.holdings[1].tolist() == expected


@pytest.mark.numba
def test_review_compiled_dispatch_preserves_supported_scope(monkeypatch):
    from doribt.runtime import compiled_schedule, compiled_targets

    calls, schedule_calls = [], []
    original = compiled_targets.execute
    original_schedule = compiled_schedule.execute

    def observed(run, info):
        calls.append(run)
        return original(run, info)

    def observed_schedule(run, info):
        schedule_calls.append(run)
        return original_schedule(run, info)

    monkeypatch.setattr(compiled_targets, "execute", observed)
    monkeypatch.setattr(compiled_schedule, "execute", observed_schedule)
    daily = data_for([10] * 5)
    quantities = {"A": [100] * 5}
    compare_review(daily, quantities, "numba", execution=BarExecution())
    assert len(calls) == 2 and not schedule_calls
    compare_review(daily, quantities, "python", execution=BarExecution())
    minute = minute_data(frequency="5min")
    compare_review(minute, {"A": [100] * 96}, "numba", execution=BarExecution())
    assert len(schedule_calls) == 2
    corporate = market_with_actions([10] * 5, [distribution()])
    result = compare_review(corporate, quantities, "numba", execution=BarExecution())
    assert result.entitlements and len(schedule_calls) == 2
    targets = WeightTargets(sessions=daily.timeline, weights={"A": [0.5] * 5})
    Backtest(daily, execution=BarExecution()).run(targets, backend="numba")
    Backtest(daily).run(
        PositionTargets(sessions=daily.timeline, quantities=quantities), backend="numba"
    )
    assert len(calls) == 2 and len(schedule_calls) == 3


@pytest.mark.numba
def test_review_subclass_and_unsupported_action_keep_original_paths(monkeypatch):
    from doribt.runtime import compiled_schedule, compiled_targets

    def forbidden(*args):
        pytest.fail("回退场景不应进入编译目标路径")

    monkeypatch.setattr(compiled_targets, "execute", forbidden)
    monkeypatch.setattr(compiled_schedule, "execute", forbidden)
    data = data_for([10] * 5)
    seen = []

    class CustomTargets(PositionTargets):
        def __call__(self, context):
            seen.append(context.bar_index)
            super().__call__(context)

    target = CustomTargets(sessions=data.timeline, quantities={"A": [100] * 5})
    Backtest(data, execution=BarExecution()).run(target, backend="numba")
    assert seen == list(range(5))
    action = distribution(kind="merger", cash_per_share=0, pay_date=None)
    corporate = market_with_actions([10] * 5, [action])
    targets = PositionTargets(sessions=corporate.timeline, quantities={"A": [100] * 5})
    test = Backtest(corporate, execution=BarExecution())
    with pytest.raises(ValueError, match="unsupported merger: d1") as actual:
        test.run(targets, backend="numba")
    with pytest.raises(ValueError) as reference:
        test.run(lambda ctx: targets(ctx), backend="numba")
    assert str(actual.value) == str(reference.value)


@pytest.mark.numba
def test_review_repeated_run_and_arrays_are_independent():
    data = data_for([10] * 5, [10] * 5, settlement=0)
    test = Backtest(data, execution=BarExecution())
    first = PositionTargets(sessions=data.timeline, quantities={"B": [100] * 5})
    other = PositionTargets(sessions=data.timeline, quantities={"A": [200] * 5})
    original = test.run(first, backend="numba")
    saved = {
        item.name: getattr(original, item.name).copy()
        for item in fields(original)
        if isinstance(getattr(original, item.name), np.ndarray)
    }
    different = test.run(other, backend="numba")
    repeated = test.run(first, backend="numba")
    assert_review_parity(original, repeated)
    assert original.run_info == repeated.run_info
    assert different.holdings[-1].tolist() == [200, 0]
    for name, snapshot in saved.items():
        value = getattr(original, name)
        assert not value.flags.writeable, name
        np.testing.assert_array_equal(value, snapshot, err_msg=name)
        if name != "close_units":
            assert not np.shares_memory(value, getattr(repeated, name)), name


@pytest.mark.parametrize("with_schema", [False, True])
def test_review_metadata_matches_previous_canonical_assembly(backend, with_schema):
    from dataclasses import replace

    from doribt import Parameter, ParameterSet, RunConfig
    from doribt.serialization import encode

    data = data_for([10] * 3)
    config = RunConfig(initial_cash=10000, costs=Costs(commission=".0003"), backend=backend)
    test = Backtest(data, config=config)
    schema = ParameterSet({"quantity": Parameter(type="int", default=100, label="数量")})

    def callback(context, *, quantity=100):
        context.target_positions({"A": quantity})

    declared = schema if with_schema else None
    actual = test.run(callback, parameter_schema=declared, backend=backend)
    with patch.object(Backtest, "_metadata", return_value={}):
        base = test.run(callback, parameter_schema=declared, backend=backend)
    expected = base.run_info.to_dict()
    effective = replace(
        config,
        initial_cash=test.initial_cash,
        costs=test.costs,
        execution=test.execution or BarExecution(),
    )
    expected["config"] = effective.to_dict() | {"backend": backend}
    if with_schema:
        expected["parameter_schema"] = schema.to_dict()
    assert actual.run_info.json == encode(expected)
