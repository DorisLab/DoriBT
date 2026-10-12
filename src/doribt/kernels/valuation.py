"""账户估值的整数内核；乘法前检查上限，保持两种后端一致。"""

from collections.abc import Callable
from functools import lru_cache
from typing import cast

from doribt.kernels.execution import IntArray
from doribt.validation import MAX_MONEY

type Valuer = Callable[[IntArray, IntArray, int], int]


def account_value(closes: IntArray, quantities: IntArray, cash: int) -> int:
    if len(closes) != len(quantities):
        raise ValueError("valuation prices and quantities must have equal lengths")
    for quantity in quantities:
        if quantity > 1_000_000_000:
            raise OverflowError("economic share quantity exceeds supported bounds")
    for column in range(len(quantities)):
        quantity, price = int(quantities[column]), int(closes[column])
        if quantity and price <= 0:
            raise ValueError("held security has no active valuation; unsupported delisting")
    equity = cash
    for column in range(len(quantities)):
        quantity, price = int(quantities[column]), int(closes[column])
        if quantity:
            if price > (MAX_MONEY - equity) // quantity:
                raise OverflowError("account equity exceeds supported bounds")
            equity += quantity * price
    if not 0 <= equity <= MAX_MONEY:
        raise OverflowError("account equity exceeds supported bounds")
    return equity


@lru_cache(maxsize=1)
def accelerated_value() -> Valuer:
    from numba import njit

    return cast(Valuer, njit(cache=True)(account_value))


def valuer(backend: str) -> Valuer:
    return accelerated_value() if backend == "numba" else account_value
