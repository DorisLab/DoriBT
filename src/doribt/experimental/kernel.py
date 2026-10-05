"""Integer-cent accounting for the explicitly limited 100-share ETF model."""

import numpy as np

from .models import MAX_CENTS


def simulate(op, close, upper, lower, suspended, regime, initial, weight, rate, minimum, slip):
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
                if suspended[i]:
                    reason = 1
                elif side == 1 and op[i] == upper[i]:
                    reason = 2
                elif side == -1 and op[i] == lower[i]:
                    reason = 3
                if reason == 0:
                    price = (
                        min(op[i] + slip, upper[i]) if side == 1 else max(op[i] - slip, lower[i])
                    )
                    # 100 shares * 0.001 yuan = 10 cents per price tick.
                    budget = available * weight // 1_000_000
                    quantity = budget // (price * 10) * 100 if side == 1 else shares
                    if quantity > MAX_CENTS * 10 // price:
                        raise ValueError("notional exceeds supported accounting bounds")
                    gross = quantity * price // 10
                    fee = max(minimum, (gross * rate + 500_000) // 1_000_000)
                    if side == 1 and gross + fee > available:
                        # Monotonic lot-cost search also handles extreme fee assumptions.
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
                        reason = 4
                    else:
                        available -= side * gross + fee
                        shares += side * quantity
                        fills[count, 0] = i
                        fills[count, 1] = j
                        fills[count, 2] = side * quantity
                        fills[count, 3] = price
                        fills[count, 4] = fee
                        count += 1
            if shares > MAX_CENTS * 10 // close[i]:
                raise ValueError("position valuation exceeds supported accounting bounds")
            value = available + shares * close[i] // 10
            if value > MAX_CENTS or available > MAX_CENTS:
                raise ValueError("account exceeds supported accounting bounds")
            cash[i, j], position[i, j], equity[i, j] = available, shares, value
            blocked[i, j] = reason
    return equity, cash, position, fills[:count], blocked
