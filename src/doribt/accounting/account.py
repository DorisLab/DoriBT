"""FIFO acquisition lots and trading-session settlement state."""

from dataclasses import dataclass
from datetime import date

import numpy as np

from doribt.accounting.orders import Order
from doribt.kernels.execution import IntArray
from doribt.kernels.valuation import Valuer, account_value


@dataclass(slots=True)
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
    frozen_quantity: int = 0

    @property
    def available_quantity(self) -> int:
        return max(0, self.sellable - self.frozen_quantity)


class Account:
    def __init__(self, initial_cash: int, symbols: tuple[str, ...]) -> None:
        self.cash = initial_cash
        self.symbols = symbols
        self.lots: list[Lot] = []
        self._columns = {symbol: column for column, symbol in enumerate(symbols)}
        self._totals = np.zeros(len(symbols), dtype=np.int64)
        self._sellable: dict[int, IntArray] = {}
        self._overflow = False
        self._last_available = -1
        self.value_kernel: Valuer = account_value
        self.changed_symbols: set[str] = set()

    def add_lot(self, lot: Lot) -> None:
        self.lots.append(lot)
        self.changed_symbols.add(lot.symbol)
        self._totals[self._columns[lot.symbol]] += lot.quantity
        self._overflow = self._overflow or self._totals[self._columns[lot.symbol]] > 1_000_000_000
        self._last_available = max(self._last_available, lot.available_session)
        self._sellable.clear()

    def quantities(self, index: int | None = None) -> IntArray:
        if index is None or index >= self._last_available:
            totals = self._totals
        else:
            if index not in self._sellable:
                settled = np.zeros(len(self.symbols), dtype=np.int64)
                for lot in self.lots:
                    if lot.available_session <= index:
                        settled[self._columns[lot.symbol]] += lot.quantity
                self._sellable = {index: settled}
            totals = self._sellable[index]
        if self._overflow and np.any(totals > 1_000_000_000):
            raise OverflowError("registered share quantity exceeds supported bounds")
        return totals.copy()

    def apply(self, order: Order, index: int, settlement: int) -> None:
        self.apply_fill(
            order.symbol, order.filled, order.session, order.price_units, index, settlement
        )

    def apply_fill(
        self, symbol: str, quantity: int, session: date, price: int, index: int, settlement: int
    ) -> None:
        if quantity > 0:
            self.add_lot(Lot(symbol, quantity, session, index + settlement, price))
        elif quantity < 0:
            self._sell(symbol, -quantity, index)

    def _sell(self, symbol: str, quantity: int, index: int) -> None:
        self.changed_symbols.add(symbol)
        for lot in self.lots:
            if lot.symbol != symbol or lot.available_session > index:
                continue
            consumed = min(quantity, lot.quantity)
            lot.quantity -= consumed
            self._totals[self._columns[symbol]] -= consumed
            quantity -= consumed
        self.lots = [lot for lot in self.lots if lot.quantity]
        self._sellable.clear()
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
        return self.value_kernel(closes, quantities, equity)
