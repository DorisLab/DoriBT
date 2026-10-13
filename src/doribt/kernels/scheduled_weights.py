"""权重目标的整数定量与意图元数据，收盘和开盘共享同一成交队列。"""

import numpy as np

from doribt.kernels.execution import OPEN, IntArray
from doribt.kernels.scheduled_orders import cancel_child
from doribt.kernels.valuation import account_value

WEIGHT, SIZING, SIZED_AT = 6, 7, 8
PRESENT, MINIMUM, BUY_STEP, SELL_STEP, SELL_MINIMUM = range(5)


def weight_size(
    equity: int,
    weight: int,
    price: int,
    current: int,
    rule: IntArray,
    index: int,
    mode: int,
    column: int,
) -> int:
    if not weight:
        return 0
    if not rule[PRESENT]:
        raise ValueError("weight_sizing", index, mode, 3, column)
    if price <= 0:
        raise ValueError("weight_sizing", index, mode, 1, column)
    # 拆分乘法避免 equity×weight 超出 int64；结果仍严格向下取整。
    budget = equity // 1_000_000 * weight + equity % 1_000_000 * weight // 1_000_000
    desired = budget // price
    if desired > 1_000_000_000:
        raise ValueError("weight_sizing", index, mode, 2, column)
    if desired > current:
        extra, minimum, step = desired - current, int(rule[MINIMUM]), int(rule[BUY_STEP])
        extra = 0 if extra < minimum else minimum + (extra - minimum) // step * step
        return current + extra
    reduction = (current - desired) // int(rule[SELL_STEP]) * int(rule[SELL_STEP])
    return current - (0 if reduction < rule[SELL_MINIMUM] else reduction)


def replace_weights(
    index: int,
    weights: IntArray,
    mode: int,
    rebalance: bool,
    equity: int,
    closes: IntArray,
    sizing_rules: IntArray,
    positions: IntArray,
    active: IntArray,
    intents: IntArray,
    count: int,
    children: IntArray,
    orders: IntArray,
    frozen: IntArray,
    shares: IntArray,
) -> int:
    if index and not rebalance and np.array_equal(weights[index], weights[index - 1]):
        return count
    # 与公开接口一致：先完成所有证券定量，再替换任何现有意图。
    quantities = np.zeros(len(active), dtype=np.int64)
    if mode == 1:
        for column in range(len(active)):
            quantities[column] = weight_size(
                equity,
                int(weights[index, column]),
                int(closes[index, column]),
                int(positions[column]),
                sizing_rules[index, column],
                index,
                mode,
                column,
            )
    for column in range(len(active)):
        previous = int(active[column])
        if previous >= 0:
            cancel_child(int(children[column]), index, orders, frozen, shares)
            intents[previous, 3:6] = index, 2, 2
        children[column] = -1
        intents[count, :6] = column, index, quantities[column], -1, 0, 0
        intents[count, 6:9] = weights[index, column], mode, index if mode == 1 else -1
        active[column] = count
        count += 1
    return count


def resolve_weights(
    index: int,
    active: IntArray,
    intents: IntArray,
    positions: IntArray,
    market: IntArray,
    sizing_rules: IntArray,
    cash: int,
) -> None:
    unsized = False
    for identifier in active:
        if (
            identifier >= 0
            and intents[identifier, SIZING] == 2
            and intents[identifier, SIZED_AT] < 0
        ):
            unsized = True
    if not unsized:
        return
    equity = account_value(market[index, :, OPEN], positions, cash)
    for column in np.argsort(active):
        identifier = int(active[column])
        if identifier < 0 or intents[identifier, SIZING] != 2 or intents[identifier, SIZED_AT] >= 0:
            continue
        intents[identifier, 2] = weight_size(
            equity,
            int(intents[identifier, WEIGHT]),
            int(market[index, column, OPEN]),
            int(positions[column]),
            sizing_rules[index, column],
            index,
            2,
            column,
        )
        intents[identifier, SIZED_AT] = index


def finish_scheduled_intents(
    index: int, active: IntArray, intents: IntArray, positions: IntArray
) -> None:
    for column in range(len(active)):
        identifier = int(active[column])
        if identifier < 0:
            continue
        unsized = intents[identifier, SIZING] == 2 and intents[identifier, SIZED_AT] < 0
        if not unsized and intents[identifier, 2] == positions[column]:
            intents[identifier, 3:6] = index, 1, 0
        else:
            intents[identifier, 3:6] = index, 3, 3
