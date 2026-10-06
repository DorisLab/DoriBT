"""Scan stable-order intervals without changing the broker or accounting state."""

from collections.abc import Callable
from functools import lru_cache
from typing import cast

import numpy as np

from doribt.kernels.execution import IntArray
from doribt.runtime.matching import accelerated, match
from doribt.validation import MAX_MONEY

type Scanner = Callable[[int, int, IntArray, IntArray, IntArray, IntArray, IntArray, IntArray], int]


def next_fill(
    start: int,
    stop: int,
    columns: IntArray,
    states: IntArray,
    market: IntArray,
    intrabar: IntArray,
    costs: IntArray,
    config: IntArray,
) -> int:
    """Return the first possible fill; all earlier bars leave resources unchanged.

    Scheduled targets have at most one active child per security. No fills means
    shared cash and participation usage cannot change; stop before the first fill
    and let the normal broker apply its sell-first ordering and reservations.
    """
    if not len(columns):
        return stop
    for index in range(start, stop):
        for item in range(len(columns)):
            column = columns[item]
            low, high, auction = intrabar[index, column]
            if not auction:
                row = match(states[item], market[index, column], costs, config, 0, low, high)
                if row[0]:
                    return index
    return stop


@lru_cache(maxsize=1)
def accelerated_scan() -> Scanner:
    accelerated()  # Register exactly the same numeric matcher helpers.
    from numba import njit
    from numba.extending import register_jitable

    register_jitable(match)
    return cast(Scanner, njit(cache=True)(next_fill))


def scanner(backend: str) -> Scanner:
    if backend == "numba":
        return accelerated_scan()
    if backend == "python":
        return next_fill
    raise ValueError("backend must be python or numba")


def value_span(closes: IntArray, quantities: IntArray, cash: int) -> IntArray:
    """Batch valuation with the same bounds as Account.value, before int64 arithmetic."""
    equity = np.full(len(closes), cash, dtype=np.int64)
    if np.any(quantities > 1_000_000_000):
        raise OverflowError("economic share quantity exceeds supported bounds")
    for column, quantity in enumerate(quantities):
        if not quantity:
            continue
        prices = closes[:, column]
        if np.any(prices <= 0):
            raise ValueError("held security has no active valuation; unsupported delisting")
        if np.any(prices > (MAX_MONEY - equity) // quantity):
            raise OverflowError("account equity exceeds supported bounds")
        equity += prices * quantity
    if np.any(equity < 0) or np.any(equity > MAX_MONEY):
        raise OverflowError("account equity exceeds supported bounds")
    return equity
