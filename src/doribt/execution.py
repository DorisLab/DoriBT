"""Integer daily open execution shared by Python and the optional JIT backend."""

from collections.abc import Callable
from functools import lru_cache
from typing import cast

import numpy as np
from numpy.typing import NDArray

from .validation import MAX_MONEY

type IntArray = NDArray[np.int64]
type Executor = Callable[
    [int, IntArray, IntArray, IntArray, IntArray, IntArray, int], tuple[int, IntArray]
]

# Market columns. Inactive and missing limits use zero; raw prices are always positive.
OPEN, STATUS, UPPER, LOWER, TICK, MINIMUM, BUY_STEP, SELL_STEP = range(8)
STAMP, TRANSFER, VOLUME, ODD_LOT = range(8, 12)
SELL_MINIMUM, ORDER_MAXIMUM = range(12, 14)
# Output: signed fill, price, commission, stamp duty, transfer fee, reason.
QUANTITY, PRICE, COMMISSION, STAMP_FEE, TRANSFER_FEE, REASON = range(6)
# Reasons, also exposed by name through Order records.
OK, SUSPENDED, INACTIVE, UPPER_BLOCK, LOWER_BLOCK, NO_VOLUME = range(6)
INVALID_QUANTITY, CASH_SHORT, SELLABLE_SHORT, POSITION_SHORT, BAD_PRICE = range(6, 11)


def fee(notional: int, rate: int) -> int:
    """Half-up to a cent without multiplying two unbounded int64 values."""
    denominator = 100_000_000
    cents = (notional // denominator) * rate
    cents += ((notional % denominator) * rate + denominator // 2) // denominator
    return cents * 100


def charges(
    value: int, commission: int, minimum: int, stamp: int, transfer: int
) -> tuple[int, int, int]:
    return max(minimum, fee(value, commission)), fee(value, stamp), fee(value, transfer)


def buy_size(requested: int, price: int, available: int, rule: IntArray, costs: IntArray) -> int:
    """Largest legal quantity including fees, with logarithmic affordability search."""
    minimum, step = int(rule[MINIMUM]), int(rule[BUY_STEP])
    if requested < minimum or (requested - minimum) % step:
        return -1
    if requested > MAX_MONEY // price:
        raise OverflowError("order notional exceeds supported bounds")
    low, high = 0, (requested - minimum) // step + 1
    while low < high:
        middle = (low + high + 1) // 2
        quantity = minimum + (middle - 1) * step
        value = quantity * price
        commission, stamp, transfer = charges(value, costs[0], costs[1], 0, rule[TRANSFER])
        if value + commission + stamp + transfer <= available:
            low = middle
        else:
            high = middle - 1
    return minimum + (low - 1) * step if low else 0


def sell_size(requested: int, position: int, sellable: int, rule: IntArray) -> tuple[int, int]:
    step = int(rule[SELL_STEP])
    liquidation = bool(rule[ODD_LOT]) and requested == position
    if (requested < rule[SELL_MINIMUM] or requested % step) and not liquidation:
        return 0, INVALID_QUANTITY
    quantity = min(requested, position, sellable)
    if not (liquidation and quantity == position):
        quantity = quantity // step * step
        if quantity < rule[SELL_MINIMUM]:
            quantity = 0
    reason = OK
    if requested > position:
        reason = POSITION_SHORT
    elif quantity < requested:
        reason = SELLABLE_SHORT
    return quantity, reason


def market_block(rule: IntArray, buying: bool, price: int) -> int:
    if rule[STATUS] == 1:
        return SUSPENDED
    if rule[STATUS] != 0:
        return INACTIVE
    if rule[VOLUME] == 0:
        return NO_VOLUME
    if buying and rule[UPPER] > 0 and rule[OPEN] >= rule[UPPER]:
        return UPPER_BLOCK
    if not buying and rule[LOWER] > 0 and rule[OPEN] <= rule[LOWER]:
        return LOWER_BLOCK
    if price <= 0 or (rule[UPPER] > 0 and price > rule[UPPER]):
        return BAD_PRICE
    if rule[LOWER] > 0 and price < rule[LOWER]:
        return BAD_PRICE
    return OK


def execute_one(
    cash: int,
    position: int,
    sellable: int,
    requested: int,
    rule: IntArray,
    costs: IntArray,
    reserved: int,
) -> tuple[int, IntArray]:
    result = np.zeros(6, dtype=np.int64)
    buying = requested > 0
    direction = 1 if buying else -1
    price = int(rule[OPEN] + direction * costs[2] * rule[TICK])
    reason = market_block(rule, buying, price)
    if reason != OK:
        result[REASON] = reason
        return cash, result
    buying_cash = max(0, cash - reserved) if buying else cash
    quantity, reason = order_size(buying_cash, position, sellable, requested, price, rule, costs)
    result[REASON] = reason
    if quantity == 0:
        return cash, result
    if quantity > MAX_MONEY // price:
        raise OverflowError("fill notional exceeds supported bounds")
    value = quantity * price
    stamp_rate = 0 if buying else int(rule[STAMP])
    commission, stamp, transfer = charges(value, costs[0], costs[1], stamp_rate, rule[TRANSFER])
    remaining = cash - direction * value - commission - stamp - transfer
    if remaining < 0:
        result[REASON] = CASH_SHORT
        return cash, result
    if remaining > MAX_MONEY:
        raise OverflowError("cash exceeds supported bounds")
    result[:5] = direction * quantity, price, commission, stamp, transfer
    return remaining, result


def order_size(
    cash: int,
    position: int,
    sellable: int,
    requested: int,
    price: int,
    rule: IntArray,
    costs: IntArray,
) -> tuple[int, int]:
    if abs(requested) > rule[ORDER_MAXIMUM]:
        return 0, INVALID_QUANTITY
    if requested < 0:
        return sell_size(-requested, position, sellable, rule)
    quantity = buy_size(requested, price, cash, rule, costs)
    if quantity < 0:
        return 0, INVALID_QUANTITY
    return quantity, CASH_SHORT if quantity < requested else OK


def simulate_open(
    cash: int,
    positions: IntArray,
    sellable: IntArray,
    requests: IntArray,
    market: IntArray,
    costs: IntArray,
    reserved: int,
) -> tuple[int, IntArray]:
    fills = np.zeros((len(requests), 6), dtype=np.int64)
    for direction in (-1, 1):
        for column in range(len(requests)):
            quantity = int(requests[column])
            if quantity * direction <= 0:
                continue
            cash, row = execute_one(
                cash, positions[column], sellable[column], quantity, market[column], costs, reserved
            )
            fills[column] = row
    return cash, fills


@lru_cache(maxsize=1)
def accelerated() -> Executor:
    try:
        from numba import njit
        from numba.extending import register_jitable
    except ImportError as error:
        raise ImportError("Numba execution requires doribt[numba]") from error
    for function in (fee, charges, buy_size, sell_size, market_block, order_size, execute_one):
        register_jitable(function)
    return cast(Executor, njit(cache=True)(simulate_open))


def executor(backend: str) -> Executor:
    if backend == "python":
        return simulate_open
    if backend == "numba":
        return accelerated()
    raise ValueError("backend must be python or numba")
