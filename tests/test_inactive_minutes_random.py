"""分钟首尾边界与固定种子混合约束；不改变历史状态以取得加速。"""

from dataclasses import replace

import numpy as np
import pytest
from inactive_fixtures import ledger, scenario
from minute_fixtures import minute_data
from test_compiled_fastpath_review import review_daily_case

from doribt import Backtest, BarExecution, Costs, FixedBps, WeightTargets
from doribt.market.instruments import TradingStatus
from doribt.serialization import encode


@pytest.mark.numba
@pytest.mark.parametrize("frequency", ["1min", "5min"])
@pytest.mark.parametrize("sizing", ["close", "execution"])
@pytest.mark.parametrize("rebalance", [False, True])
@pytest.mark.parametrize("before_listing", [False, True])
def test_minute_listing_boundary(frequency, sizing, rebalance, before_listing):
    span = 240 if frequency == "1min" else 48
    inactive = dict(
        status="unlisted",
        open=None,
        high=None,
        low=None,
        close=None,
        upper_limit=None,
        lower_limit=None,
        volume=0,
    )
    data = minute_data(
        days=3,
        frequency=frequency,
        symbols=("A", "B"),
        changes={index * 2: inactive for index in range(span)},
        settlement=1,
        volume=137,
    )
    periods = tuple(
        replace(p, start=data.sessions[1]) if p.symbol == "A" else p for p in data.rules.periods
    )
    data = replace(data, rules=replace(data.rules, periods=periods))
    start = span - int(before_listing)
    count = len(data.timeline)
    weights = [0] * start + [0.5] * (count - start)
    target = WeightTargets(
        sessions=data.timeline,
        weights={"A": weights, "B": [0.5] * count},
        sizing=sizing,
        rebalance=rebalance,
    )
    test = Backtest(data, initial_cash=10_000, execution=BarExecution(participation=".3"))
    if before_listing and sizing == "close":
        from test_inactive_errors import failure

        assert failure(test, target, "numba") == failure(test, lambda ctx: target(ctx), "python")
        return
    reference = test.run(lambda ctx: target(ctx))
    compiled = test.run(target, backend="numba")
    assert encode(ledger(compiled)) == encode(ledger(reference))
    assert compiled.run_info.to_dict()["execution_plan"]["plan"] == "compiled_targets"
    first = next(fill for fill in compiled.fills if fill.symbol == "A")
    assert first.session == data.sessions[1]


@pytest.mark.numba
@pytest.mark.parametrize("seed", range(20))
def test_seeded_weights_with_listing_rules_cash_and_volume(seed):
    data, _ = review_daily_case(seed)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, 6, size=3)
    bars = tuple(
        replace(
            bar,
            status=TradingStatus.UNLISTED,
            open=0,
            high=0,
            low=0,
            close=0,
            volume=0,
            upper_limit=None,
            lower_limit=None,
        )
        if index // 3 < starts[index % 3]
        else bar
        for index, bar in enumerate(data.bars)
    )
    periods = tuple(
        replace(p, start=data.sessions[int(starts[data.symbols.index(p.symbol)])])
        if p.start == data.sessions[0]
        else p
        for p in data.rules.periods
    )
    data = replace(data, bars=bars, rules=replace(data.rules, periods=periods))
    weights = rng.choice([0, 0.1, 0.2, 0.3], size=(16, 3))
    for column, start in enumerate(starts):
        weights[:start, column] = 0
    target = WeightTargets(
        sessions=data.timeline,
        weights={s: weights[:, c] for c, s in enumerate(data.symbols)},
        sizing="close" if seed % 2 else "execution",
        rebalance=bool(seed % 3),
    )
    test = Backtest(
        data,
        initial_cash=1000,
        costs=Costs(commission=".003", minimum_commission=5),
        execution=BarExecution(
            participation=".17",
            slippage=FixedBps(7),
            slippage_policy=("strict", "cap", "cost")[seed % 3],
        ),
    )
    reference = test.run(lambda ctx: target(ctx))
    compiled = test.run(target, backend="numba")
    assert encode(ledger(compiled)) == encode(ledger(reference)), seed


@pytest.mark.numba
@pytest.mark.parametrize("name", ["never", "listing", "delisted", "pending_delisted"])
def test_single_security_lifecycle(name):
    data, target = scenario(name, symbols=("A",))
    test = Backtest(data, execution=BarExecution())
    assert encode(ledger(test.run(target, backend="numba"))) == encode(
        ledger(test.run(lambda ctx: target(ctx)))
    )
