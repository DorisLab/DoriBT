"""持仓批次的数值 FIFO 链与交收事件堆。"""

from doribt.kernels.execution import IntArray

COLUMN, QUANTITY, ACQUIRED, AVAILABLE, PRICE, PREVIOUS, NEXT = range(7)
LOT_COUNT, EVENT_COUNT, CURRENT_DAY = range(3)
OVERFLOW_SEEN = 3


def event_push(lot: int, data: IntArray, heap: IntArray, state: IntArray) -> None:
    position = int(state[EVENT_COUNT])
    state[EVENT_COUNT] += 1
    while position:
        parent = (position - 1) // 2
        if data[heap[parent], AVAILABLE] <= data[lot, AVAILABLE]:
            break
        heap[position] = heap[parent]
        position = parent
    heap[position] = lot


def event_pop(data: IntArray, heap: IntArray, state: IntArray) -> int:
    result = int(heap[0])
    state[EVENT_COUNT] -= 1
    count = int(state[EVENT_COUNT])
    if count == 0:
        return result
    lot = int(heap[count])
    position = 0
    while position * 2 + 1 < count:
        child = position * 2 + 1
        if child + 1 < count and data[heap[child + 1], AVAILABLE] < data[heap[child], AVAILABLE]:
            child += 1
        if data[lot, AVAILABLE] <= data[heap[child], AVAILABLE]:
            break
        heap[position] = heap[child]
        position = child
    heap[position] = lot
    return result


def ledger_rewind(
    day: int, data: IntArray, heap: IntArray, state: IntArray, settled: IntArray
) -> None:
    # 非单调查询必须针对当前存活批次重建，不能使用历史持仓快照。
    settled[:] = 0
    state[EVENT_COUNT] = 0
    for lot in range(int(state[LOT_COUNT])):
        quantity = int(data[lot, QUANTITY])
        if quantity == 0:
            continue
        if data[lot, AVAILABLE] <= day:
            settled[data[lot, COLUMN]] += quantity
        else:
            event_push(lot, data, heap, state)


def ledger_advance(
    day: int, data: IntArray, heap: IntArray, state: IntArray, settled: IntArray
) -> None:
    if day < state[CURRENT_DAY]:
        ledger_rewind(day, data, heap, state, settled)
    while state[EVENT_COUNT] and data[heap[0], AVAILABLE] <= day:
        lot = event_pop(data, heap, state)
        settled[data[lot, COLUMN]] += data[lot, QUANTITY]
    state[CURRENT_DAY] = day


def unlink_lot(lot: int, column: int, data: IntArray, heads: IntArray, tails: IntArray) -> None:
    previous, following = int(data[lot, PREVIOUS]), int(data[lot, NEXT])
    if previous < 0:
        heads[column] = following
    else:
        data[previous, NEXT] = following
    if following < 0:
        tails[column] = previous
    else:
        data[following, PREVIOUS] = previous


def ledger_sell(
    quantity: int,
    column: int,
    data: IntArray,
    heads: IntArray,
    tails: IntArray,
    state: IntArray,
    totals: IntArray,
    settled: IntArray,
) -> None:
    lot = int(heads[column])
    while lot >= 0 and quantity:
        following = int(data[lot, NEXT])
        if data[lot, AVAILABLE] <= state[CURRENT_DAY]:
            consumed = min(quantity, int(data[lot, QUANTITY]))
            data[lot, QUANTITY] -= consumed
            totals[column] -= consumed
            settled[column] -= consumed
            quantity -= consumed
            if data[lot, QUANTITY] == 0:
                unlink_lot(lot, column, data, heads, tails)
        lot = following
    if quantity:
        raise RuntimeError("execution sold more than settled lots")


def ledger_fill(
    quantity: int,
    column: int,
    ordinal: int,
    available: int,
    price: int,
    data: IntArray,
    heads: IntArray,
    tails: IntArray,
    heap: IntArray,
    state: IntArray,
    totals: IntArray,
    settled: IntArray,
) -> None:
    # 调用方先推进交收日并扩容；内核不持有 Python 对象。
    if quantity <= 0:
        if quantity < 0:
            ledger_sell(-quantity, column, data, heads, tails, state, totals, settled)
        return
    if quantity > 9_223_372_036_854_775_807 - totals[column]:
        raise OverflowError("registered share quantity exceeds supported bounds")
    lot = int(state[LOT_COUNT])
    previous = int(tails[column])
    data[lot, COLUMN] = column
    data[lot, QUANTITY] = quantity
    data[lot, ACQUIRED] = ordinal
    data[lot, AVAILABLE] = available
    data[lot, PRICE] = price
    data[lot, PREVIOUS] = previous
    data[lot, NEXT] = -1
    if previous >= 0:
        data[previous, NEXT] = lot
    else:
        heads[column] = lot
    tails[column] = lot
    state[LOT_COUNT] += 1
    totals[column] += quantity
    if len(state) > OVERFLOW_SEEN and totals[column] > 1_000_000_000:
        state[OVERFLOW_SEEN] = 1
    if available <= state[CURRENT_DAY]:
        settled[column] += quantity
    else:
        event_push(lot, data, heap, state)


def register_ledger() -> None:
    from numba.extending import register_jitable

    for function in (
        event_push,
        event_pop,
        ledger_rewind,
        ledger_advance,
        unlink_lot,
        ledger_sell,
        ledger_fill,
    ):
        register_jitable(function)
