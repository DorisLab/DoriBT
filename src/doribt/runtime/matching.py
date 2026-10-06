"""Numeric partial-fill matcher. Python and Numba execute the identical equations."""

from collections.abc import Callable
from functools import lru_cache
from typing import cast

import numpy as np

from doribt.kernels.execution import (
    BAD_PRICE,
    CASH_SHORT,
    LOWER,
    OK,
    OPEN,
    STAMP,
    TICK,
    TRANSFER,
    UPPER,
    VOLUME,
    IntArray,
    fee,
    market_block,
)
from doribt.validation import MAX_MONEY

CAPACITY, LIMIT_PRICE, AUCTION = 11, 12, 13
# State: remaining quantity, cumulative notional, commission paid, cash budget,
#        reserved sellable shares, limit price (0 means market).
LEFT, NOTIONAL, PAID, BUDGET, RESERVED, LIMIT = range(6)
STRICT, CAP, COST = range(3)
type Matcher = Callable[[IntArray, IntArray, IntArray, IntArray, int, int, int], IntArray]


def slip_price(rule: IntArray, config: IntArray, quantity: int, used: int, buying: bool) -> int:
    op, tick = int(rule[OPEN]), int(rule[TICK])
    direction = 1 if buying else -1
    if not tick:
        return op
    if config[1] == 0:
        return op + direction * int(config[2]) * tick
    ppm = int(config[2])
    if config[1] == 2:
        share = min(1.0, (used + quantity) / max(1, int(rule[VOLUME])))
        # Impact is an explicit floating-point modelling assumption, money remains integer.
        impact = op * ppm / 1_000_000 * share * share
        ticks = int(np.ceil(impact / tick))
    else:
        # Quotient/remainder avoids overflowing op * ppm.
        delta = op // 1_000_000 * ppm
        delta += (op % 1_000_000 * ppm + 999_999) // 1_000_000
        ticks = (delta + tick - 1) // tick
    return op + direction * ticks * tick


def fill_costs(
    quantity: int, price: int, buying: bool, state: IntArray, rule: IntArray, costs: IntArray
) -> tuple[int, int, int]:
    if price <= 0 or quantity > MAX_MONEY // price:
        raise OverflowError("fill notional exceeds supported bounds")
    value = quantity * price
    if state[NOTIONAL] > MAX_MONEY - value:
        raise OverflowError("cumulative order notional exceeds supported bounds")
    commission = max(int(costs[1]), fee(int(state[NOTIONAL]) + value, int(costs[0])))
    commission -= int(state[PAID])
    return (
        commission,
        fee(value, 0 if buying else int(rule[STAMP])),
        fee(value, int(rule[TRANSFER])),
    )


def settlement_price(price: int, policy: int, low: int, high: int) -> int:
    # 仅 cap 减少滑点；cost 保留成本假设，strict 留待价格保护检查。
    if policy == CAP:
        return min(high, max(low, price))
    return price


def affordable(
    quantity: int,
    state: IntArray,
    rule: IntArray,
    costs: IntArray,
    config: IntArray,
    used: int,
    price_low: int,
    price_high: int,
) -> int:
    low, high = 0, quantity
    while low < high:
        middle = (low + high + 1) // 2
        price = slip_price(rule, config, middle, used, True)
        price = settlement_price(price, int(config[3]), price_low, price_high)
        fees = fill_costs(middle, price, True, state, rule, costs)
        if middle * price + sum(fees) <= state[BUDGET]:
            low = middle
        else:
            high = middle - 1
    return low


def price_block(price: int, buying: bool, state: IntArray, low: int, high: int, policy: int) -> int:
    if price <= 0:
        return BAD_PRICE
    if policy == STRICT and (price < low or price > high):
        return BAD_PRICE
    limit = int(state[LIMIT])
    if limit and (price > limit if buying else price < limit):
        return LIMIT_PRICE
    return OK


def fill_size(
    state: IntArray,
    rule: IntArray,
    costs: IntArray,
    config: IntArray,
    used: int,
    capacity: int,
    low: int,
    high: int,
) -> tuple[int, int]:
    wanted = abs(int(state[LEFT]))
    capped = min(wanted, max(0, capacity - used))
    if state[LEFT] > 0:
        quantity = affordable(capped, state, rule, costs, config, used, low, high)
        short = CASH_SHORT
    else:
        quantity = min(capped, int(state[RESERVED]))
        short = 8
    reason = OK if quantity == wanted else CAPACITY
    if quantity < capped:
        reason = short
    return quantity, reason


def match(
    state: IntArray,
    rule: IntArray,
    costs: IntArray,
    config: IntArray,
    used: int,
    low: int,
    high: int,
) -> IntArray:
    row = np.zeros(6, dtype=np.int64)
    buying = state[LEFT] > 0
    reason = market_block(rule, buying, int(rule[OPEN]))
    if reason:
        row[5] = reason
        return row
    low = max(low, int(rule[LOWER]))
    high = min(high, int(rule[UPPER])) if rule[UPPER] else high
    if low > high:
        row[5] = BAD_PRICE
        return row
    capacity = int(rule[VOLUME]) // 1_000_000 * int(config[0])
    capacity += int(rule[VOLUME]) % 1_000_000 * int(config[0]) // 1_000_000
    quantity, size_reason = fill_size(state, rule, costs, config, used, capacity, low, high)
    if not quantity:
        row[5] = size_reason
        return row
    price = slip_price(rule, config, quantity, used, buying)
    price = settlement_price(price, int(config[3]), low, high)
    reason = price_block(price, buying, state, low, high, int(config[3]))
    if reason:
        row[5] = reason
        return row
    charges = fill_costs(quantity, price, buying, state, rule, costs)
    row[:5] = quantity if buying else -quantity, price, charges[0], charges[1], charges[2]
    row[5] = size_reason
    return row


@lru_cache(maxsize=1)
def accelerated() -> Matcher:
    try:
        from numba import njit
        from numba.extending import register_jitable
    except ImportError as error:
        raise ImportError("Numba execution requires doribt[numba]") from error
    for function in (
        fee,
        market_block,
        slip_price,
        fill_costs,
        settlement_price,
        affordable,
        price_block,
        fill_size,
    ):
        register_jitable(function)
    return cast(Matcher, njit(cache=True)(match))


def matcher(backend: str) -> Matcher:
    if backend == "python":
        return match
    if backend == "numba":
        return accelerated()
    raise ValueError("backend must be python or numba")
