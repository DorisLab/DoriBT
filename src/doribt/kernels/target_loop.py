"""将日线目标、申报、撮合和账本推进编译为一个数值循环。"""

from collections.abc import Callable
from functools import lru_cache
from typing import cast

import numpy as np

from doribt.kernels.execution import IntArray, charges
from doribt.kernels.reservation import reservation_cost
from doribt.kernels.target_ledger import (
    empty_state,
    finish_intents,
    place_targets,
    reconcile_lots,
    settle_fill,
)
from doribt.kernels.target_orders import (
    COLUMN,
    QUANTITY,
    REASON,
    attempt,
    child_quantity,
    submission_code,
    submit_children,
)
from doribt.kernels.valuation import account_value
from doribt.runtime.matching import accelerated, match

type TargetKernel = Callable[
    [IntArray, IntArray, IntArray, IntArray, IntArray, IntArray, IntArray, IntArray, int],
    tuple[IntArray, ...],
]


def execute_children(
    index: int,
    start: int,
    stop: int,
    orders: IntArray,
    budgets: IntArray,
    positions: IntArray,
    available: IntArray,
    releases: IntArray,
    market: IntArray,
    intrabar: IntArray,
    settlement: IntArray,
    costs: IntArray,
    config: IntArray,
    cash: int,
    frozen: int,
    fills: IntArray,
    fill_count: int,
) -> tuple[int, int]:
    for buying in (False, True):
        for order_id in range(start, stop):
            order = orders[order_id]
            quantity, column = int(order[QUANTITY]), int(order[COLUMN])
            if order[REASON] or (quantity > 0) != buying:
                continue
            budget = int(budgets[column])
            previous_cash = cash
            cash, filled = attempt(
                order,
                index,
                cash,
                frozen,
                budget,
                positions,
                available,
                market[index],
                intrabar[index],
                costs,
                config,
            )
            if buying:
                released = budget if filled == quantity else min(budget, previous_cash - cash)
                frozen -= released
            settle_fill(index, column, filled, settlement, positions, available, releases)
            if filled:
                fills[fill_count] = order_id
                fill_count += 1
    return cash, fill_count


def simulate_targets(
    targets: IntArray,
    columns: IntArray,
    market: IntArray,
    closes: IntArray,
    intrabar: IntArray,
    settlement: IntArray,
    costs: IntArray,
    config: IntArray,
    initial_cash: int,
) -> tuple[IntArray, ...]:
    days, width = closes.shape
    capacity = max(0, days - 1) * len(columns)
    orders = np.zeros((capacity, 12), dtype=np.int64)
    intents = np.zeros((targets.size, 6), dtype=np.int64)
    lots = np.zeros((capacity, 4), dtype=np.int64)
    fills = np.zeros(capacity, dtype=np.int64)
    positions, available, active = empty_state(width)
    heads, tails = active.copy(), active.copy()
    releases = np.zeros_like(closes)
    holdings, sellable = np.zeros_like(closes), np.zeros_like(closes)
    cashes, equity = np.zeros(days, dtype=np.int64), np.zeros(days, dtype=np.int64)
    cash = initial_cash
    order_count, intent_count, lot_count, fill_count = 0, 0, 0, 0
    for index in range(days):
        available += releases[index]
        previous = positions.copy()
        if index:
            budgets = np.zeros(width, dtype=np.int64)
            start = order_count
            order_count, frozen = submit_children(
                index,
                active,
                intents,
                positions,
                market,
                closes,
                costs,
                config,
                cash,
                orders,
                order_count,
                budgets,
            )
            cash, fill_count = execute_children(
                index,
                start,
                order_count,
                orders,
                budgets,
                positions,
                available,
                releases,
                market,
                intrabar,
                settlement,
                costs,
                config,
                cash,
                frozen,
                fills,
                fill_count,
            )
        lot_count = reconcile_lots(index, positions - previous, lots, heads, tails, lot_count)
        holdings[index], sellable[index] = positions, available
        cashes[index] = cash
        equity[index] = account_value(closes[index], positions, cash)
        intent_count = place_targets(index, targets, columns, active, intents, intent_count)
    finish_intents(days - 1, active, intents, positions)
    return (
        equity,
        cashes,
        holdings,
        sellable,
        orders[:order_count],
        intents[:intent_count],
        lots[:lot_count],
        fills[:fill_count],
    )


@lru_cache(maxsize=1)
def compiled_targets() -> TargetKernel:
    accelerated()
    from numba import njit
    from numba.extending import register_jitable

    for function in (
        charges,
        reservation_cost,
        match,
        child_quantity,
        submission_code,
        submit_children,
        attempt,
        settle_fill,
        reconcile_lots,
        place_targets,
        finish_intents,
        empty_state,
        execute_children,
        account_value,
    ):
        register_jitable(function)
    return cast(TargetKernel, njit(cache=True)(simulate_targets))
