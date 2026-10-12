"""FIFO acquisition lots and trading-session settlement state."""

from dataclasses import dataclass
from datetime import date

import numpy as np

from doribt.accounting.orders import Order
from doribt.kernels.account_ledger import (
    ACQUIRED,
    AVAILABLE,
    COLUMN,
    LOT_COUNT,
    OVERFLOW_SEEN,
    PRICE,
    QUANTITY,
    ledger_advance,
    ledger_fill,
)
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
        self._columns = {symbol: column for column, symbol in enumerate(symbols)}
        self._totals = np.zeros(len(symbols), dtype=np.int64)
        self._settled = np.zeros(len(symbols), dtype=np.int64)
        self._lot_data = np.zeros((16, 7), dtype=np.int64)
        self._lot_heads = np.full(len(symbols), -1, dtype=np.int64)
        self._lot_tails = np.full(len(symbols), -1, dtype=np.int64)
        self._event_heap = np.empty(16, dtype=np.int64)
        self._ledger_state = np.array([0, 0, -1, 0], dtype=np.int64)
        self.value_kernel: Valuer = account_value
        self.changed_symbols: set[str] = set()

    @property
    def lots(self) -> list[Lot]:
        # 仅在显式检查批次时构造 Python 记录，日常成交只更新数值缓冲区。
        records = self._lot_data[: int(self._ledger_state[LOT_COUNT])]
        return [
            Lot(
                self.symbols[int(row[COLUMN])],
                int(row[QUANTITY]),
                date.fromordinal(int(row[ACQUIRED])),
                int(row[AVAILABLE]),
                int(row[PRICE]),
            )
            for row in records
            if row[QUANTITY]
        ]

    def reserve_lots(self, extra: int) -> None:
        needed = int(self._ledger_state[LOT_COUNT]) + extra
        if needed <= len(self._lot_data):
            return
        capacity = max(needed, len(self._lot_data) * 2)
        data = np.zeros((capacity, 7), dtype=np.int64)
        data[: len(self._lot_data)] = self._lot_data
        heap = np.empty(capacity, dtype=np.int64)
        heap[: len(self._event_heap)] = self._event_heap
        self._lot_data, self._event_heap = data, heap

    def advance_day(self, index: int) -> None:
        ledger_advance(index, self._lot_data, self._event_heap, self._ledger_state, self._settled)

    def add_lot(self, lot: Lot) -> None:
        self.reserve_lots(1)
        self.changed_symbols.add(lot.symbol)
        ledger_fill(
            lot.quantity,
            self._columns[lot.symbol],
            lot.acquired.toordinal(),
            lot.available_session,
            lot.price_units,
            self._lot_data,
            self._lot_heads,
            self._lot_tails,
            self._event_heap,
            self._ledger_state,
            self._totals,
            self._settled,
        )

    def quantities(self, index: int | None = None) -> IntArray:
        totals = self._totals
        if index is not None:
            self.advance_day(index)
            totals = self._settled
        # 溢出标记只增不减，避免可卖量查询掩盖尚未交收的超限总持仓。
        overflow = len(self._ledger_state) <= OVERFLOW_SEEN or self._ledger_state[OVERFLOW_SEEN]
        if overflow and np.any(totals > 1_000_000_000):
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
        self.advance_day(index)
        ledger_fill(
            -quantity,
            self._columns[symbol],
            0,
            0,
            0,
            self._lot_data,
            self._lot_heads,
            self._lot_tails,
            self._event_heap,
            self._ledger_state,
            self._totals,
            self._settled,
        )

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
