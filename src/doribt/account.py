"""FIFO acquisition lots and trading-session settlement state."""

from dataclasses import dataclass
from datetime import date

import numpy as np

from .execution import IntArray
from .orders import Order
from .validation import MAX_MONEY


@dataclass
class Lot:
    symbol: str
    quantity: int
    acquired: date
    available_session: int
    price_units: int


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: int
    sellable: int
    value: float
    pending_quantity: int = 0


class Account:
    def __init__(self, initial_cash: int, symbols: tuple[str, ...]) -> None:
        self.cash = initial_cash
        self.symbols = symbols
        self.lots: list[Lot] = []

    def quantities(self, index: int | None = None) -> IntArray:
        totals = dict.fromkeys(self.symbols, 0)
        for lot in self.lots:
            if index is None or lot.available_session <= index:
                totals[lot.symbol] += lot.quantity
        if any(quantity > 1_000_000_000 for quantity in totals.values()):
            raise OverflowError("registered share quantity exceeds supported bounds")
        return np.array(list(totals.values()), dtype=np.int64)

    def apply(self, order: Order, index: int, settlement: int) -> None:
        if order.filled > 0:
            self.lots.append(
                Lot(
                    order.symbol, order.filled, order.session, index + settlement, order.price_units
                )
            )
        elif order.filled < 0:
            self._sell(order.symbol, -order.filled, index)

    def _sell(self, symbol: str, quantity: int, index: int) -> None:
        for lot in self.lots:
            if lot.symbol != symbol or lot.available_session > index:
                continue
            consumed = min(quantity, lot.quantity)
            lot.quantity -= consumed
            quantity -= consumed
        self.lots = [lot for lot in self.lots if lot.quantity]
        if quantity:
            raise RuntimeError("execution sold more than settled lots")

    def value(
        self,
        closes: IntArray,
        pending_shares: IntArray | None = None,
        receivable: int = 0,
        tax_payable: int = 0,
    ) -> int:
        equity = self.cash + receivable - tax_payable
        quantities = self.quantities()
        if pending_shares is not None:
            quantities = quantities + pending_shares
        if np.any(quantities > 1_000_000_000):
            raise OverflowError("economic share quantity exceeds supported bounds")
        for quantity, price in zip(quantities, closes, strict=True):
            if quantity and price <= 0:
                raise ValueError("held security has no active valuation; unsupported delisting")
            equity += int(quantity) * int(price)
        if not 0 <= equity <= MAX_MONEY:
            raise OverflowError("account equity exceeds supported bounds")
        return equity
