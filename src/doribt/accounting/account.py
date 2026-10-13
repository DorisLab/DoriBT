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
from doribt.kernels.ledger_state import LedgerState, allocate_ledger, grow_ledger
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
        self._ledger = allocate_ledger(16, len(symbols))
        self.value_kernel: Valuer = account_value
        self.changed_symbols: set[str] = set()

    @property
    def lots(self) -> list[Lot]:
        # 仅在显式检查批次时构造 Python 记录，日常成交只更新数值缓冲区。
        ledger = self._ledger
        records = ledger.lots[: int(ledger.control[LOT_COUNT])]
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
        self._ledger = grow_ledger(self._ledger, extra)

    def numeric_state(self) -> LedgerState:
        """返回当前数值账本；扩容后调用者必须重新取得此状态。"""
        return self._ledger

    def advance_day(self, index: int) -> None:
        ledger = self._ledger
        ledger_advance(index, ledger.lots, ledger.heap, ledger.control, ledger.settled)

    def add_lot(self, lot: Lot) -> None:
        self.reserve_lots(1)
        self.changed_symbols.add(lot.symbol)
        ledger = self._ledger
        ledger_fill(
            lot.quantity,
            self._columns[lot.symbol],
            lot.acquired.toordinal(),
            lot.available_session,
            lot.price_units,
            ledger.lots,
            ledger.heads,
            ledger.tails,
            ledger.heap,
            ledger.control,
            ledger.totals,
            ledger.settled,
        )

    def quantities(self, index: int | None = None) -> IntArray:
        ledger = self._ledger
        totals = ledger.totals
        if index is not None:
            self.advance_day(index)
            totals = ledger.settled
        # 溢出标记只增不减，避免可卖量查询掩盖尚未交收的超限总持仓。
        overflow = len(ledger.control) <= OVERFLOW_SEEN or ledger.control[OVERFLOW_SEEN]
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
        ledger = self._ledger
        ledger_fill(
            -quantity,
            self._columns[symbol],
            0,
            0,
            0,
            ledger.lots,
            ledger.heads,
            ledger.tails,
            ledger.heap,
            ledger.control,
            ledger.totals,
            ledger.settled,
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
