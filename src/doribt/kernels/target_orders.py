"""日线预计算目标的数值申报、冻结与撮合步骤。"""

import numpy as np

from doribt.kernels.execution import (
    BUY_STEP,
    MINIMUM,
    ODD_LOT,
    ORDER_MAXIMUM,
    SELL_MINIMUM,
    SELL_STEP,
    TICK,
    IntArray,
)
from doribt.kernels.reservation import reservation_cost
from doribt.runtime.matching import match
from doribt.validation import MAX_MONEY

# 委托行：意图、证券、申报日、成交日、数量、成交、价格、佣金、印花、过户、原因、状态。
(
    INTENT,
    COLUMN,
    CREATED,
    SESSION,
    QUANTITY,
    FILLED,
    PRICE,
    COMMISSION,
    STAMP,
    TRANSFER,
    REASON,
    STATE,
) = range(12)
REJECTED, FILLED_STATE, EXPIRED = range(3)


def child_quantity(difference: int, rule: IntArray) -> int:
    if not rule[TICK]:
        return 0
    maximum = int(rule[ORDER_MAXIMUM])
    if maximum and abs(difference) > maximum:
        if difference < 0:
            difference = -(maximum // int(rule[SELL_STEP]) * int(rule[SELL_STEP]))
        else:
            minimum, step = int(rule[MINIMUM]), int(rule[BUY_STEP])
            difference = minimum + (maximum - minimum) // step * step
    if difference > 0:
        minimum, step = int(rule[MINIMUM]), int(rule[BUY_STEP])
        if difference < minimum:
            return 0
        difference = minimum + (difference - minimum) // step * step
    return difference


def submission_code(quantity: int, position: int, rule: IntArray) -> int:
    size = abs(quantity)
    if size > rule[ORDER_MAXIMUM] or not rule[TICK]:
        return 6
    if quantity > 0:
        valid = size >= rule[MINIMUM] and (size - rule[MINIMUM]) % rule[BUY_STEP] == 0
    else:
        valid = size >= rule[SELL_MINIMUM] and size % rule[SELL_STEP] == 0
        valid = valid or bool(rule[ODD_LOT] and size == position)
    return 0 if valid else 6


def submit_children(
    index: int,
    active: IntArray,
    intents: IntArray,
    positions: IntArray,
    market: IntArray,
    closes: IntArray,
    costs: IntArray,
    config: IntArray,
    cash: int,
    orders: IntArray,
    count: int,
    budgets: IntArray,
) -> tuple[int, int]:
    frozen = 0
    for column in np.argsort(active):
        intent = int(active[column])
        if intent < 0:
            continue
        difference = int(intents[intent, 2] - positions[column])
        if not difference:
            intents[intent, 3:6] = index, 1, 0
            active[column] = -1
            continue
        rule = market[index - 1, column]
        quantity = child_quantity(difference, rule)
        if not quantity:
            if rule[TICK] and difference > 0:
                intents[intent, 5] = 1
            continue
        reason = submission_code(quantity, int(positions[column]), rule)
        orders[count, :5] = intent, column, index - 1, index - 1, quantity
        orders[count, REASON] = reason
        if not reason and quantity > 0:
            cost = reservation_cost(
                rule, config, costs, quantity, 0, int(closes[index - 1, column]), False
            )
            budgets[column] = min(max(0, cash - frozen), cost)
            frozen += int(budgets[column])
        count += 1
    return count, frozen


def attempt(
    order: IntArray,
    index: int,
    cash: int,
    frozen: int,
    budget: int,
    positions: IntArray,
    available: IntArray,
    market: IntArray,
    intrabar: IntArray,
    costs: IntArray,
    config: IntArray,
) -> tuple[int, int]:
    column, quantity = int(order[COLUMN]), int(order[QUANTITY])
    state = np.zeros(6, dtype=np.int64)
    state[0] = quantity
    state[3] = max(0, cash - frozen + budget) if quantity > 0 else 0
    state[4] = min(-quantity, int(available[column])) if quantity < 0 else 0
    row = np.zeros(6, dtype=np.int64)
    if intrabar[column, 2]:
        row[5] = 13
    else:
        row = match(
            state,
            market[column],
            costs,
            config,
            0,
            int(intrabar[column, 0]),
            int(intrabar[column, 1]),
        )
    if row[5] == 8 and -quantity > positions[column]:
        row[5] = 9
    cost = int(row[0] * row[1] + row[2] + row[3] + row[4])
    if row[0] < 0 and cash - cost < frozen:
        row[:] = 0, 0, 0, 0, 0, 7
        cost = 0
    cash -= cost
    if not 0 <= cash <= MAX_MONEY:
        raise OverflowError("cash exceeds supported bounds")
    order[SESSION] = index
    order[FILLED:STATE] = row
    order[STATE] = FILLED_STATE if row[0] == quantity else EXPIRED
    return cash, int(row[0])
