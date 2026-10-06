"""Independent vectorbt adapter for minute_case's bounded single-ETF protocol.

vectorbt owns cash, positions, fill records and valuation. This module does not
import DoriBT execution/accounting code. State is per independent parameter account.
"""

import importlib
from typing import Any

import numpy as np
from numpy.typing import NDArray

nb = importlib.import_module("vectorbt.portfolio.nb")
vbt = importlib.import_module("vectorbt")
njit = importlib.import_module("numba").njit
type IntArray = NDArray[np.int64]

# Per column: remaining, budget, notional, commission paid, settled, active.


def commission(value: int) -> int:
    return max(50000, (value * 3 + 500000) // 1000000 * 100)


commission_nb = njit(cache=True)(commission)


def start(c: Any, prices: IntArray, targets: IntArray, state: IntArray) -> None:
    i, col = c.i, c.col
    if i == 0 or prices[i, 6] != prices[i - 1, 6]:
        state[col, 4] = int(c.position_now)
        state[col, 5] = 0
    changed = i == 1 or i > 1 and targets[i - 1, col] != targets[i - 2, col]
    if changed:
        state[col, 5] = 0
    if i == 0 or state[col, 5]:
        return
    desired = int(targets[i - 1, col]) - int(c.position_now)
    if desired > 0:
        desired = desired // 100 * 100
    if desired == 0:
        return
    state[col, 0] = desired
    value = desired * (prices[i - 1, 3] + 10)
    state[col, 1] = value + commission_nb(value) if desired > 0 else 0
    state[col, 2:4] = 0
    state[col, 5] = 1


start_nb = njit(cache=True)(start)


def buy_size(cap: int, price: int, available: int, value: int, paid: int) -> int:
    low, high = 0, cap
    while low < high:
        q = (low + high + 1) // 2
        cost = q * price + commission_nb(value + q * price) - paid
        if cost <= available:
            low = q
        else:
            high = q - 1
    return low


buy_size_nb = njit(cache=True)(buy_size)


def order(c: Any, prices: IntArray, targets: IntArray, state: IntArray) -> Any:
    start_nb(c, prices, targets, state)
    i, col = c.i, c.col
    if not state[col, 5] or prices[i, 7] or not prices[i, 4]:
        return nb.order_nothing_nb()
    buying = state[col, 0] > 0
    price = prices[i, 0] + (10 if buying else -10)
    if price < prices[i, 2] or price > prices[i, 1]:
        return nb.order_nothing_nb()
    if buying and prices[i, 0] >= prices[i, 8] or not buying and prices[i, 0] <= prices[i, 9]:
        return nb.order_nothing_nb()
    cap = min(abs(state[col, 0]), prices[i, 4] // 1000)
    if buying:
        available = min(state[col, 1], int(np.floor(c.cash_now * 10000 + 0.5)))
        cap = buy_size_nb(cap, price, available, state[col, 2], state[col, 3])
    else:
        cap = min(cap, state[col, 4])
    if cap == 0:
        return nb.order_nothing_nb()
    return issue_nb(col, cap, price, buying, state)


def issue(col: int, cap: int, price: int, buying: bool, state: IntArray) -> Any:
    new_value = state[col, 2] + cap * price
    fee = commission_nb(new_value) - state[col, 3]
    state[col, 2], state[col, 3] = new_value, state[col, 3] + fee
    signed = cap if buying else -cap
    state[col, 0] -= signed
    if buying:
        state[col, 1] -= cap * price + fee
    else:
        state[col, 4] -= cap
    if state[col, 0] == 0:
        state[col, 5] = 0
    return nb.order_nb(
        size=signed,
        price=price / 10000,
        fees=0,
        fixed_fees=fee / 10000,
        direction=0,
        min_size=1,
        size_granularity=1,
        allow_partial=False,
        raise_reject=True,
    )


issue_nb = njit(cache=True)(issue)
order_nb = njit(cache=True)(order)


def run(prices: IntArray, targets: IntArray) -> dict[str, Any]:
    state = np.zeros((targets.shape[1], 6), dtype=np.int64)
    close = np.broadcast_to(prices[:, 3:4] / 10000, targets.shape)
    portfolio = vbt.Portfolio.from_order_func(
        close,
        order_nb,
        prices,
        targets,
        state,
        init_cash=100000,
        cash_sharing=False,
        group_by=False,
        update_value=False,
        freq="1min",
    )
    records = portfolio.orders.records_arr
    return dict(
        cash=np.asarray(portfolio.cash()),
        holdings=np.asarray(portfolio.assets()),
        equity=np.asarray(portfolio.value()),
        fills=records.copy(),
    )
