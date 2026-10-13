"""日线与分钟预计算目标复用通用撮合队列和数值批次账本。"""

from collections.abc import Callable
from functools import lru_cache
from typing import cast

import numpy as np

from doribt.kernels.account_ledger import ledger_advance
from doribt.kernels.broker_loop import compiled_queue, execute_queue, release_order
from doribt.kernels.broker_state import (
    ACTIVATION,
    EXPIRED,
    SUBMITTED,
    UNEXECUTED,
    UPDATED,
    WIDTH,
)
from doribt.kernels.buffers import grow_table
from doribt.kernels.execution import IntArray
from doribt.kernels.ledger_state import allocate_ledger, grow_ledger
from doribt.kernels.reservation import reservation_cost
from doribt.kernels.scheduled_orders import (
    active_ids,
    cancel_child,
    issue_target,
    ready_child,
    replace_targets,
    submit_target,
    sync_targets,
)
from doribt.kernels.scheduled_weights import (
    finish_scheduled_intents,
    replace_weights,
    resolve_weights,
    weight_size,
)
from doribt.kernels.target_ledger import reconcile_lots
from doribt.kernels.target_orders import child_quantity, submission_code
from doribt.kernels.valuation import account_value

type ScheduledKernel = Callable[
    [
        IntArray,
        IntArray,
        IntArray,
        IntArray,
        IntArray,
        IntArray,
        IntArray,
        IntArray,
        IntArray,
        IntArray,
        int,
        IntArray,
    ],
    tuple[IntArray, ...],
]


def expire_day(
    index: int,
    day: int,
    children: IntArray,
    orders: IntArray,
    frozen: IntArray,
    shares: IntArray,
) -> None:
    for identifier in active_ids(children, orders):
        row = orders[identifier - 1]
        if row[SUBMITTED] < index and row[ACTIVATION] <= day:
            release_order(row, frozen, shares, EXPIRED)
            row[UPDATED] = index


def finish_orders(
    index: int,
    children: IntArray,
    orders: IntArray,
    frozen: IntArray,
    shares: IntArray,
) -> None:
    for identifier in active_ids(children, orders):
        row = orders[identifier - 1]
        release_order(row, frozen, shares, UNEXECUTED)
        row[UPDATED] = index


def simulate_schedule(
    targets: IntArray,
    columns: IntArray,
    market: IntArray,
    closes: IntArray,
    intrabar: IntArray,
    settlement: IntArray,
    costs: IntArray,
    config: IntArray,
    days: IntArray,
    ordinals: IntArray,
    initial_cash: int,
    options: IntArray,
) -> tuple[IntArray, ...]:
    count, width = closes.shape
    capacity = max(16, len(columns) * 2)
    orders = np.zeros((capacity, WIDTH), dtype=np.int64)
    intents = np.zeros((capacity, 9), dtype=np.int64)
    fills = np.zeros((capacity, 7), dtype=np.int64)
    ledger = allocate_ledger(capacity, width)
    active, children = np.full(width, -1, dtype=np.int64), np.full(width, -1, dtype=np.int64)
    tax_lots = np.zeros((capacity, 4), dtype=np.int64)
    heads, tails = active.copy(), active.copy()
    previous, changed = np.zeros(width, dtype=np.int64), np.zeros(width, dtype=np.int64)
    money, frozen = np.array([initial_cash, 0], dtype=np.int64), np.zeros(1, dtype=np.int64)
    shares = np.zeros(width, dtype=np.int64)
    holdings, sellable, reserved = (
        np.zeros_like(closes),
        np.zeros_like(closes),
        np.zeros_like(closes),
    )
    equity, cash = np.zeros(count, dtype=np.int64), np.zeros(count, dtype=np.int64)
    reserved_cash = np.zeros(count, dtype=np.int64)
    order_count, intent_count, fill_count, lot_count = 0, 0, 0, 0
    for index in range(count):
        orders = grow_table(orders, order_count, len(columns))
        intents = grow_table(intents, intent_count, len(columns))
        fills = grow_table(fills, fill_count, len(columns))
        tax_lots = grow_table(tax_lots, lot_count, len(columns))
        ledger = grow_ledger(ledger, len(columns))
        day = int(days[index])
        ledger_advance(day, ledger.lots, ledger.heap, ledger.control, ledger.settled)
        if index:
            resolve_weights(index, active, intents, ledger.totals, market, int(money[0]))
            order_count = sync_targets(
                index,
                active,
                intents,
                children,
                ledger.totals,
                ledger.settled,
                market,
                closes,
                days,
                costs,
                config,
                money,
                frozen,
                shares,
                orders,
                order_count,
            )
        fill_count = execute_queue(
            active_ids(children, orders),
            orders,
            index,
            day,
            int(ordinals[day]),
            market[index],
            intrabar[index],
            settlement[index],
            costs,
            config,
            money,
            frozen,
            shares,
            ledger,
            fills,
            fill_count,
            changed,
        )
        if index + 1 == count or days[index + 1] != day:
            expire_day(index, day, children, orders, frozen, shares)
            lot_count = reconcile_lots(
                day, ledger.totals - previous, tax_lots, heads, tails, lot_count
            )
            previous[:] = ledger.totals
        holdings[index], sellable[index], reserved[index] = ledger.totals, ledger.settled, shares
        cash[index], reserved_cash[index] = money[0], frozen[0]
        equity[index] = account_value(closes[index], ledger.totals, int(money[0]))
        intent_count = place_decisions(
            index,
            targets,
            columns,
            options,
            int(equity[index]),
            closes,
            market,
            ledger.totals,
            active,
            intents,
            intent_count,
            children,
            orders,
            frozen,
            shares,
        )
    finish_scheduled_intents(count - 1, active, intents, ledger.totals)
    finish_orders(count - 1, children, orders, frozen, shares)
    return (
        equity,
        cash,
        holdings,
        sellable,
        orders[:order_count],
        intents[:intent_count],
        tax_lots[:lot_count],
        fills[:fill_count],
        reserved_cash,
        reserved,
    )


def place_decisions(
    index: int,
    targets: IntArray,
    columns: IntArray,
    options: IntArray,
    equity: int,
    closes: IntArray,
    market: IntArray,
    positions: IntArray,
    active: IntArray,
    intents: IntArray,
    count: int,
    children: IntArray,
    orders: IntArray,
    frozen: IntArray,
    shares: IntArray,
) -> int:
    if not options[0]:
        return replace_targets(
            index, targets, columns, active, intents, count, children, orders, frozen, shares
        )
    return replace_weights(
        index,
        targets,
        int(options[0]),
        bool(options[1]),
        equity,
        closes,
        market,
        positions,
        active,
        intents,
        count,
        children,
        orders,
        frozen,
        shares,
    )


@lru_cache(maxsize=1)
def compiled_schedule() -> ScheduledKernel:
    compiled_queue()
    from numba import njit
    from numba.extending import register_jitable

    for function in (
        grow_table,
        grow_ledger,
        reservation_cost,
        child_quantity,
        submission_code,
        execute_queue,
        allocate_ledger,
        active_ids,
        cancel_child,
        submit_target,
        ready_child,
        issue_target,
        sync_targets,
        replace_targets,
        expire_day,
        finish_orders,
        weight_size,
        replace_weights,
        resolve_weights,
        place_decisions,
        finish_scheduled_intents,
        reconcile_lots,
        account_value,
    ):
        register_jitable(function)
    return cast(ScheduledKernel, njit(cache=True)(simulate_schedule))
