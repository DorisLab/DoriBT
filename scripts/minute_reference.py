"""Independent Decimal oracle for the published, single-ETF minute workload.

No broker, sizing, slippage, fee or execution helpers are imported from the engine.
It deliberately uses a linear affordability search and a small explicit state.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import numpy as np
from numpy.typing import NDArray

from doribt import BacktestResult, MarketData

D = Decimal


@dataclass
class Child:
    left: int
    budget: Decimal
    value: Decimal = D(0)
    paid: Decimal = D(0)


def _charge(value: Decimal) -> Decimal:
    return max(D(5), (value * D(".0003")).quantize(D(".01"), rounding=ROUND_HALF_UP))


def reference(data: MarketData, targets: NDArray[np.int64]) -> dict[str, Any]:
    if data.actions or len(data.symbols) != 1 or data.clock is None:
        raise ValueError("reference scope: one minute ETF, no corporate actions")
    cash, quantity, available = D(100000), 0, 0
    target, child = 0, None
    cash_rows, holdings, equity, fills = [], [], [], []
    for index, bar in enumerate(data.bars):
        first = index == 0 or bar.session != data.bars[index - 1].session
        last = index + 1 == len(data.bars) or data.bars[index + 1].session != bar.session
        if first:
            available = quantity
        if index and target != quantity and child is None:
            child = _child(data, index, target - quantity)
        if child is not None:
            signed, price, commission = _execute(bar, child, cash, available)
            if signed:
                cash -= D(signed) * price + commission
                quantity += signed
                available += min(0, signed)
                fills.append(
                    [str(bar.timestamp), signed, int(price * 10000), int(commission * 10000)]
                )
            if not child.left or last:
                child = None
        cash_rows.append(int(cash * 10000))
        holdings.append(quantity)
        equity.append(int(cash * 10000) + quantity * bar.close)
        if int(targets[index]) != target:
            target, child = int(targets[index]), None
    return dict(cash=cash_rows, holdings=holdings, equity=equity, fills=fills)


def _child(data: MarketData, index: int, difference: int) -> Child | None:
    previous = data.bars[index - 1]
    quantity = difference // 100 * 100 if difference > 0 else difference
    if not quantity:
        return None
    # Published workload: domestic equity ETF tick .001, DAY orders, fixed 1-tick slip.
    value = D(quantity) * (D(previous.close) / 10000 + D(".001"))
    return Child(quantity, value + _charge(value) if quantity > 0 else D(0))


def _execute(bar: Any, child: Child, cash: Decimal, available: int) -> tuple[int, Decimal, Decimal]:
    buying = child.left > 0
    op = D(bar.open) / 10000
    price = op + (D(".001") if buying else -D(".001"))
    if bar.phase != "continuous" or int(bar.status) != 0 or not bar.volume:
        return 0, price, D(0)
    boundary = bar.upper_limit if buying else bar.lower_limit
    if boundary is not None and (bar.open >= boundary if buying else bar.open <= boundary):
        return 0, price, D(0)
    if not D(bar.low) / 10000 <= price <= D(bar.high) / 10000:
        return 0, price, D(0)
    volume_cap = int(D(bar.volume) * D(".001"))
    size = min(abs(child.left), volume_cap, abs(child.left) if buying else available)
    while size:
        value = D(size) * price
        commission = _charge(child.value + value) - child.paid
        if not buying or value + commission <= min(cash, child.budget):
            child.value += value
            child.paid += commission
            signed = size if buying else -size
            child.left -= signed
            if buying:
                child.budget -= value + commission
            return signed, price, commission
        size -= 1
    return 0, price, D(0)


def verify(result: BacktestResult, expected: dict[str, Any]) -> None:
    # Explicit failures remain enabled under python -O.
    for name, actual in (
        ("cash", result.cash_units),
        ("holdings", result.holdings[:, 0]),
        ("equity", result.equity_units),
    ):
        if not np.array_equal(actual, expected[name]):
            index = int(np.flatnonzero(actual != expected[name])[0])
            raise ValueError(
                f"independent {name} mismatch at bar {index}: "
                f"{actual[index]} != {expected[name][index]}"
            )
    fills = [
        [str(fill.timestamp), fill.quantity, fill.price_units, fill.commission_units]
        for fill in result.fills
    ]
    if fills != expected["fills"]:
        raise ValueError("independent fills mismatch")
