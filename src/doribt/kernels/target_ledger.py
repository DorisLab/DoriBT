"""无公司行动日线的交收和独立日末税务批次。"""

import numpy as np

from doribt.kernels.execution import IntArray


def settle_fill(
    index: int,
    column: int,
    quantity: int,
    settlement: IntArray,
    positions: IntArray,
    available: IntArray,
    releases: IntArray,
) -> None:
    positions[column] += quantity
    if quantity < 0:
        available[column] += quantity
    elif quantity:
        when = index + int(settlement[index, column])
        if when == index:
            available[column] += quantity
        elif when < len(releases):
            releases[when, column] += quantity


def reconcile_lots(
    index: int,
    changes: IntArray,
    lots: IntArray,
    heads: IntArray,
    tails: IntArray,
    count: int,
) -> int:
    # 税务按日末证券列序编号；卖出消耗税务 FIFO，而不是交收批次。
    for column in range(len(changes)):
        change = int(changes[column])
        if change > 0:
            lots[count] = column, index, change, -1
            if heads[column] < 0:
                heads[column] = count
            else:
                lots[tails[column], 3] = count
            tails[column] = count
            count += 1
        elif change < 0:
            left = -change
            while left:
                head = int(heads[column])
                consumed = min(left, int(lots[head, 2]))
                lots[head, 2] -= consumed
                left -= consumed
                if not lots[head, 2]:
                    heads[column] = lots[head, 3]
    return count


def place_targets(
    index: int,
    targets: IntArray,
    columns: IntArray,
    active: IntArray,
    intents: IntArray,
    count: int,
) -> int:
    # 调用者的映射顺序决定意图 ID；不可替换成证券排序。
    for offset in range(len(columns)):
        quantity = int(targets[index, offset])
        if index and quantity == targets[index - 1, offset]:
            continue
        column = int(columns[offset])
        previous = int(active[column])
        if previous >= 0:
            intents[previous, 3:6] = index, 2, 2
        intents[count] = column, index, quantity, -1, 0, 0
        active[column] = count
        count += 1
    return count


def finish_intents(index: int, active: IntArray, intents: IntArray, positions: IntArray) -> None:
    for column in range(len(active)):
        intent = int(active[column])
        if intent >= 0:
            if intents[intent, 2] == positions[column]:
                intents[intent, 3:6] = index, 1, 0
            else:
                intents[intent, 3:6] = index, 3, 3


def empty_state(columns: int) -> tuple[IntArray, IntArray, IntArray]:
    return (
        np.zeros(columns, dtype=np.int64),
        np.zeros(columns, dtype=np.int64),
        np.full(columns, -1, dtype=np.int64),
    )
