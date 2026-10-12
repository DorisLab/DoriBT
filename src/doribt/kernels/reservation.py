"""买单冻结估值，两个后端共用同一费用与滑点公式。"""

from collections.abc import Callable
from functools import lru_cache
from typing import cast

from doribt.kernels.execution import OPEN, TRANSFER, IntArray, charges
from doribt.runtime.matching import accelerated, slip_price
from doribt.validation import MAX_MONEY

type Reservation = Callable[[IntArray, IntArray, IntArray, int, int, int, bool], int]


def reservation_cost(
    rule: IntArray,
    config: IntArray,
    costs: IntArray,
    quantity: int,
    limit: int,
    close: int,
    execution: bool,
) -> int:
    price = int(rule[OPEN])
    if not execution:
        rule = rule.copy()
        rule[OPEN] = close
        price = limit or slip_price(rule, config, quantity, 0, True)
    if price <= 0 or quantity > MAX_MONEY // price:
        raise OverflowError("order reservation exceeds supported bounds")
    notional = quantity * price
    commission, stamp, transfer = charges(
        notional, int(costs[0]), int(costs[1]), 0, int(rule[TRANSFER])
    )
    return notional + commission + stamp + transfer


@lru_cache(maxsize=1)
def accelerated_reservation() -> Reservation:
    accelerated()
    from numba import njit
    from numba.extending import register_jitable

    register_jitable(charges)
    return cast(Reservation, njit(cache=True)(reservation_cost))


def reservation(backend: str) -> Reservation:
    return accelerated_reservation() if backend == "numba" else reservation_cost
