"""独立随机分钟样本：保留规则、事件掩码、完整订单及日末税务语义。"""

import numpy as np
from minute_fixtures import minute_data
from test_compiled_fastpath_review import assert_review_parity

from doribt import (
    Backtest,
    BarExecution,
    Costs,
    FixedBps,
    FixedTicks,
    PositionTargets,
    VolumeImpact,
)


def minute_random_case(backend, seed):
    rng = np.random.default_rng(8000 + seed)
    count, width = 144, 3
    changes = {}
    for row in range(count * width):
        price = int(rng.integers(8, 13))
        volume = int(rng.choice([0, 31, 101, 9999]))
        suspended = rng.random() < 0.06
        changes[row] = dict(
            open=price,
            close=price,
            high=12,
            low=8,
            volume=0 if suspended else volume,
            status="suspended" if suspended else "trading",
            phase="auction" if rng.random() < 0.03 else "continuous",
        )
    data = minute_data(
        days=3,
        frequency="5min",
        symbols=("A", "B", "C"),
        settlement=seed % 3,
        changes=changes,
        rule_changes=dict(
            order_maximum=500,
            sell_minimum=100,
            sell_step=100,
            allow_odd_lot_liquidation=bool(seed % 2),
            stamp_duty_sell=".0005",
            transfer_fee=".00001",
        ),
    )
    quantities = {}
    for symbol in reversed(data.symbols):
        values = rng.choice([0, 47, 99, 100, 200, 333, 800], size=count).tolist()
        if seed % 2:
            values = [values[index // 13 * 13] for index in range(count)]
        quantities[symbol] = values
    target = PositionTargets(sessions=data.timeline, quantities=quantities)
    execution = BarExecution(
        participation=(".01", ".17", 1)[seed % 3],
        slippage=(FixedTicks(1), FixedBps(7), VolumeImpact(".2"))[seed % 3],
        slippage_policy=("strict", "cap", "cost")[seed % 3],
    )
    test = Backtest(
        data,
        initial_cash=1500 if seed % 2 else 10000,
        costs=Costs(commission=".0003", minimum_commission=5),
        execution=execution,
    )
    result = test.run(target, backend=backend)
    reference = test.run(lambda ctx: target(ctx), backend=backend)
    assert_review_parity(result, reference)
    return result, ()
