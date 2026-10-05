"""Integer-cent accounting for the explicitly limited 100-share ETF model."""

import numpy as np

from .models import MAX_CENTS
from .typing import BoolArray, FlagArray, IntArray, KernelOutput


def market_block(side: int, op: int, upper: int, lower: int, suspended: bool) -> int:
    if suspended:
        return 1
    if side == 1 and op == upper:
        return 2
    if side == -1 and op == lower:
        return 3
    return 0


def execution(
    side: int,
    price: int,
    available: int,
    shares: int,
    weight: int,
    rate: int,
    minimum: int,
) -> tuple[int, int, int]:
    """Size and charge a fill; zero quantity never charges a fee."""
    budget = available * weight // 1_000_000
    quantity = budget // (price * 10) * 100 if side == 1 else shares
    if quantity > MAX_CENTS * 10 // price:
        raise ValueError("notional exceeds supported accounting bounds")
    gross = quantity * price // 10
    fee = max(minimum, (gross * rate + 500_000) // 1_000_000)
    if side == 1 and gross + fee > available:
        low, high = 0, quantity // 100
        while low < high:
            mid = (low + high + 1) // 2
            amount = mid * price * 10
            cost = max(minimum, (amount * rate + 500_000) // 1_000_000)
            if amount + cost <= available:
                low = mid
            else:
                high = mid - 1
        quantity = low * 100
        gross = quantity * price // 10
        fee = max(minimum, (gross * rate + 500_000) // 1_000_000)
    if quantity == 0 or (side == -1 and available + gross < fee):
        return 0, 0, 0
    return quantity, gross, fee


def valuation(available: int, shares: int, close: int) -> int:
    if shares > MAX_CENTS * 10 // close:
        raise ValueError("position valuation exceeds supported accounting bounds")
    value = available + shares * close // 10
    if value > MAX_CENTS or available > MAX_CENTS:
        raise ValueError("account exceeds supported accounting bounds")
    return value


def simulate(
    op: IntArray,
    close: IntArray,
    upper: IntArray,
    lower: IntArray,
    suspended: BoolArray,
    regime: FlagArray,
    initial: int,
    weight: int,
    rate: int,
    minimum: int,
    slip: int,
) -> KernelOutput:
    n, m = regime.shape
    equity = np.empty((n, m), dtype=np.int64)
    cash = np.empty((n, m), dtype=np.int64)
    position = np.empty((n, m), dtype=np.int64)
    blocked = np.zeros((n, m), dtype=np.int8)
    fills = np.empty((n * m, 5), dtype=np.int64)
    count = 0
    for j in range(m):
        available, shares = initial, 0
        for i in range(n):
            side = 0
            if regime[i, j] and shares == 0:
                side = 1
            elif not regime[i, j] and shares > 0:
                side = -1
            reason = 0
            if side:
                reason = market_block(side, op[i], upper[i], lower[i], suspended[i])
                if reason == 0:
                    price = (
                        min(op[i] + slip, upper[i]) if side == 1 else max(op[i] - slip, lower[i])
                    )
                    quantity, gross, fee = execution(
                        side, price, available, shares, weight, rate, minimum
                    )
                    if quantity == 0:
                        reason = 4
                    else:
                        available -= side * gross + fee
                        shares += side * quantity
                        fills[count] = (i, j, side * quantity, price, fee)
                        count += 1
            cash[i, j] = available
            position[i, j] = shares
            equity[i, j] = valuation(available, shares, close[i])
            blocked[i, j] = reason
    return equity, cash, position, fills[:count], blocked
