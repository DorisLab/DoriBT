"""预计算意图通过通用订单数组提交，保留分钟日内有效期与重试策略。"""

import numpy as np

from doribt.kernels.broker_loop import release_order
from doribt.kernels.broker_state import (
    ACTIVATION,
    BUYING,
    CANCELLED,
    CEILING,
    COLUMN,
    COMPLETE,
    INTENT,
    QUANTITY,
    REASON,
    REJECTED,
    SESSION,
    SPEND,
    STATE,
    SUBMITTED,
    UPDATED,
    VALID,
)
from doribt.kernels.execution import TICK, IntArray
from doribt.kernels.reservation import reservation_cost
from doribt.kernels.target_orders import child_quantity, submission_code
from doribt.validation import MAX_MONEY


def active_ids(children: IntArray, orders: IntArray) -> IntArray:
    values = np.zeros(len(children), dtype=np.int64)
    count = 0
    for child in children:
        if child >= 0 and orders[child, STATE] in (0, 2):
            values[count] = child + 1
            count += 1
    return np.sort(values[:count])


def cancel_child(
    child: int,
    index: int,
    orders: IntArray,
    frozen: IntArray,
    shares: IntArray,
) -> None:
    if child >= 0 and orders[child, STATE] in (0, 2):
        release_order(orders[child], frozen, shares, CANCELLED)
        orders[child, UPDATED] = index


def submit_target(
    index: int,
    column: int,
    intent: int,
    quantity: int,
    rule: IntArray,
    close: int,
    execution_sizing: bool,
    days: IntArray,
    positions: IntArray,
    settled: IntArray,
    costs: IntArray,
    config: IntArray,
    money: IntArray,
    frozen: IntArray,
    shares: IntArray,
    order: IntArray,
) -> None:
    reason = submission_code(quantity, int(positions[column]), rule)
    order[0], order[COLUMN], order[QUANTITY] = quantity, column, quantity
    order[SUBMITTED], order[SESSION], order[UPDATED] = index - 1, index - 1, index - 1
    order[ACTIVATION], order[SPEND], order[BUYING] = days[index], MAX_MONEY, quantity > 0
    order[INTENT], order[VALID], order[CEILING], order[REASON] = intent + 1, 1, -1, reason
    if reason:
        order[STATE] = REJECTED
    elif quantity > 0:
        cost = reservation_cost(rule, config, costs, quantity, 0, close, execution_sizing)
        budget = min(max(0, int(money[0] - money[1] - frozen[0])), cost)
        order[3] = budget
        frozen[0] += budget
    else:
        # 提交视图仍是前一 bar 的可卖量；开盘撮合会重新冻结新交收股份。
        reserved = min(-quantity, max(0, int(settled[column] - shares[column])))
        order[4] = reserved
        shares[column] += reserved


def sync_targets(
    index: int,
    active: IntArray,
    intents: IntArray,
    children: IntArray,
    positions: IntArray,
    settled: IntArray,
    market: IntArray,
    closes: IntArray,
    days: IntArray,
    costs: IntArray,
    config: IntArray,
    money: IntArray,
    frozen: IntArray,
    shares: IntArray,
    orders: IntArray,
    count: int,
) -> int:
    for column in np.argsort(active):
        intent = int(active[column])
        if intent < 0:
            continue
        difference = int(intents[intent, 2] - positions[column])
        child = int(children[column])
        if not difference:
            cancel_child(child, index - 1, orders, frozen, shares)
            children[column] = -1
            intents[intent, 3:6] = index, 1, 0
            active[column] = -1
        elif ready_child(child, index, days, orders):
            count = issue_target(
                index,
                column,
                intent,
                difference,
                children,
                intents,
                positions,
                settled,
                market,
                closes,
                days,
                costs,
                config,
                money,
                frozen,
                shares,
                orders,
                count,
            )
    return count


def ready_child(child: int, index: int, days: IntArray, orders: IntArray) -> bool:
    if child < 0:
        return True
    order = orders[child]
    if order[STATE] in (0, 2):
        return False
    return bool(order[STATE] == COMPLETE or days[int(order[SESSION])] != days[index])


def issue_target(
    index: int,
    column: int,
    intent: int,
    difference: int,
    children: IntArray,
    intents: IntArray,
    positions: IntArray,
    settled: IntArray,
    market: IntArray,
    closes: IntArray,
    days: IntArray,
    costs: IntArray,
    config: IntArray,
    money: IntArray,
    frozen: IntArray,
    shares: IntArray,
    orders: IntArray,
    count: int,
) -> int:
    execution_sizing = intents[intent, 7] == 2
    rule = market[index if execution_sizing else index - 1, column]
    quantity = child_quantity(difference, rule)
    if not quantity:
        if rule[TICK] and difference > 0:
            intents[intent, 5] = 1
        return count
    submit_target(
        index,
        column,
        intent,
        quantity,
        rule,
        int(closes[index - 1, column]),
        execution_sizing,
        days,
        positions,
        settled,
        costs,
        config,
        money,
        frozen,
        shares,
        orders[count],
    )
    children[column] = count
    return count + 1


def replace_targets(
    index: int,
    values: IntArray,
    columns: IntArray,
    active: IntArray,
    intents: IntArray,
    count: int,
    children: IntArray,
    orders: IntArray,
    frozen: IntArray,
    shares: IntArray,
) -> int:
    for offset in range(len(columns)):
        quantity = int(values[index, offset])
        if index and quantity == values[index - 1, offset]:
            continue
        column, previous = int(columns[offset]), int(active[columns[offset]])
        if previous >= 0:
            cancel_child(int(children[column]), index, orders, frozen, shares)
            intents[previous, 3:6] = index, 2, 2
        children[column] = -1
        intents[count, :6] = column, index, quantity, -1, 0, 0
        intents[count, 6:9] = -1, 0, -1
        active[column] = count
        count += 1
    return count
