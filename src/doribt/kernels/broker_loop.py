"""在一次调用内完成共享资金订单队列撮合，记录完整资金与成交状态。"""

from collections.abc import Callable
from functools import lru_cache
from typing import cast

import numpy as np

from doribt.kernels.account_ledger import ledger_fill, register_ledger
from doribt.kernels.broker_state import (
    BUYING,
    COLUMN,
    COMPLETE,
    EXPIRED,
    FILLED,
    PARTIAL,
    PRICE,
    REASON,
    SESSION,
    SPEND,
    STAMP_PAID,
    STATE,
    SUBMITTED,
    TRANSFER_PAID,
    UPDATED,
    VALID,
)
from doribt.kernels.execution import IntArray
from doribt.runtime.matching import BUDGET, LEFT, NOTIONAL, PAID, RESERVED, accelerated, match
from doribt.validation import MAX_MONEY

type QueueKernel = Callable[
    [
        IntArray,
        IntArray,
        int,
        int,
        int,
        IntArray,
        IntArray,
        IntArray,
        IntArray,
        IntArray,
        IntArray,
        IntArray,
        IntArray,
        tuple[IntArray, ...],
        IntArray,
        int,
        IntArray,
    ],
    int,
]


def release_order(order: IntArray, frozen: IntArray, shares: IntArray, state: int) -> None:
    frozen[0] -= order[BUDGET]
    shares[int(order[COLUMN])] -= order[RESERVED]
    order[BUDGET], order[RESERVED], order[STATE] = 0, 0, state


def reserve_sale(order: IntArray, settled: IntArray, shares: IntArray) -> None:
    column = int(order[COLUMN])
    shares[column] -= order[RESERVED]
    order[RESERVED] = min(-int(order[LEFT]), max(0, int(settled[column] - shares[column])))
    shares[column] += order[RESERVED]


def validate_registered(positions: IntArray) -> None:
    for quantity in positions:
        if quantity > 1_000_000_000:
            raise OverflowError("registered share quantity exceeds supported bounds")


def match_order(
    order: IntArray,
    market: IntArray,
    intrabar: IntArray,
    costs: IntArray,
    config: IntArray,
    used: IntArray,
    money: IntArray,
    frozen: IntArray,
    positions: IntArray,
) -> IntArray:
    column = int(order[COLUMN])
    state = order[:6].copy()
    available = max(0, int(money[0] - money[1] - frozen[0] + order[BUDGET]))
    if order[BUYING]:
        state[BUDGET] = min(available, int(order[SPEND]))
    row = np.zeros(6, dtype=np.int64)
    if intrabar[column, 2]:
        row[5] = 13
    else:
        row = match(
            state,
            market[column],
            costs,
            config,
            int(used[column]),
            int(intrabar[column, 0]),
            int(intrabar[column, 1]),
        )
    if row[5] == 8:
        validate_registered(positions)
        if -order[LEFT] > positions[column]:
            row[5] = 9
    if row[5] == 7 and order[SPEND] < available:
        row[5] = 14
    cost = int(row[0] * row[1] + row[2] + row[3] + row[4])
    if row[0] < 0 and money[0] - cost < frozen[0]:
        row[:] = 0, 0, 0, 0, 0, 7
    return row


def apply_order(
    order: IntArray,
    row: IntArray,
    index: int,
    money: IntArray,
    frozen: IntArray,
    shares: IntArray,
) -> None:
    quantity, price, commission, stamp, transfer, reason = row
    column = int(order[COLUMN])
    if quantity:
        cost = int(quantity * price + commission + stamp + transfer)
        money[0] -= cost
        if not 0 <= money[0] <= MAX_MONEY:
            raise OverflowError("cash exceeds supported bounds")
        order[LEFT] -= quantity
        order[NOTIONAL] += abs(quantity) * price
        order[PAID] += commission
        order[PRICE] = price
        if quantity > 0:
            budget = max(0, int(order[BUDGET]) - cost)
            frozen[0] += budget - order[BUDGET]
            order[BUDGET] = budget
            order[SPEND] -= cost
        else:
            order[RESERVED] += quantity
            shares[column] += quantity
    order[FILLED] += quantity
    order[STAMP_PAID] += stamp
    order[TRANSFER_PAID] += transfer
    order[REASON], order[SESSION], order[UPDATED] = reason, index, index
    order[STATE] = PARTIAL if order[FILLED] else 0
    if not order[LEFT]:
        release_order(order, frozen, shares, COMPLETE)
    elif not order[VALID]:
        release_order(order, frozen, shares, EXPIRED)


def execute_queue(
    ids: IntArray,
    orders: IntArray,
    index: int,
    day: int,
    ordinal: int,
    market: IntArray,
    intrabar: IntArray,
    settlement: IntArray,
    costs: IntArray,
    config: IntArray,
    money: IntArray,
    frozen: IntArray,
    shares: IntArray,
    ledger: tuple[IntArray, ...],
    fills: IntArray,
    fill_count: int,
    changed: IntArray,
) -> int:
    used = np.zeros(len(shares), dtype=np.int64)
    for buying in (False, True):
        for identifier in ids:
            order = orders[identifier - 1]
            if order[SUBMITTED] >= index or bool(order[BUYING]) != buying:
                continue
            if not buying:
                reserve_sale(order, ledger[6], shares)
            row = match_order(
                order, market, intrabar, costs, config, used, money, frozen, ledger[5]
            )
            apply_order(order, row, index, money, frozen, shares)
            column, quantity = int(order[COLUMN]), int(row[0])
            if quantity:
                fill_count = apply_ledger_fill(
                    identifier,
                    index,
                    day,
                    ordinal,
                    column,
                    row,
                    settlement,
                    ledger,
                    fills,
                    fill_count,
                )
                changed[column] = 1
            used[column] += abs(quantity)
    return fill_count


def apply_ledger_fill(
    identifier: int,
    index: int,
    day: int,
    ordinal: int,
    column: int,
    row: IntArray,
    settlement: IntArray,
    ledger: tuple[IntArray, ...],
    fills: IntArray,
    count: int,
) -> int:
    ledger_fill(
        int(row[0]),
        column,
        ordinal,
        day + int(settlement[column]),
        int(row[1]),
        ledger[0],
        ledger[1],
        ledger[2],
        ledger[3],
        ledger[4],
        ledger[5],
        ledger[6],
    )
    fills[count, :2] = identifier, index
    fills[count, 2:] = row[:5]
    return count + 1


@lru_cache(maxsize=1)
def compiled_queue() -> QueueKernel:
    accelerated()
    register_ledger()
    from numba import njit
    from numba.extending import register_jitable

    for function in (
        match,
        validate_registered,
        release_order,
        reserve_sale,
        match_order,
        apply_order,
        apply_ledger_fill,
    ):
        register_jitable(function)
    return cast(QueueKernel, njit(cache=True)(execute_queue))
