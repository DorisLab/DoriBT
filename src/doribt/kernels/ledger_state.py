"""账户与编译队列共用的具名数值账本状态。"""

from typing import NamedTuple

import numpy as np

from doribt.kernels.account_ledger import EVENT_COUNT, LOT_COUNT
from doribt.kernels.buffers import grow_table
from doribt.kernels.execution import IntArray


class LedgerState(NamedTuple):
    lots: IntArray
    heads: IntArray
    tails: IntArray
    heap: IntArray
    control: IntArray
    totals: IntArray
    settled: IntArray


def allocate_ledger(capacity: int, width: int) -> LedgerState:
    if capacity < 1 or width < 0:
        raise ValueError("ledger capacity must be positive and width must be nonnegative")
    return LedgerState(
        np.zeros((capacity, 7), dtype=np.int64),
        np.full(width, -1, dtype=np.int64),
        np.full(width, -1, dtype=np.int64),
        np.zeros(capacity, dtype=np.int64),
        np.array([0, 0, -1, 0], dtype=np.int64),
        np.zeros(width, dtype=np.int64),
        np.zeros(width, dtype=np.int64),
    )


def grow_ledger(state: LedgerState, extra: int) -> LedgerState:
    lots = grow_table(state.lots, int(state.control[LOT_COUNT]), extra)
    if len(lots) == len(state.lots):
        return state
    heap = np.zeros(len(lots), dtype=np.int64)
    count = int(state.control[EVENT_COUNT])
    heap[:count] = state.heap[:count]
    return LedgerState(
        lots, state.heads, state.tails, heap, state.control, state.totals, state.settled
    )
