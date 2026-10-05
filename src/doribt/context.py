"""Public close callback with a time-limited history and immutable account view."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

import numpy as np
from numpy.typing import NDArray

from .account import Position
from .data import MarketData
from .intents import IntentBook
from .orders import IntentRecord, Order
from .validation import Number, integer, ratio


@dataclass(frozen=True)
class AccountView:
    cash: float
    equity: float
    positions: Mapping[str, Position]
    frozen_cash: float = 0.0
    dividend_receivable: float = 0.0
    tax_payable: float = 0.0

    @property
    def available_cash(self) -> float:
        return max(0.0, self.cash - self.tax_payable)


class Context:
    def __init__(
        self,
        data: MarketData,
        index: int,
        history: Mapping[str, NDArray[np.float64]],
        account: AccountView,
        orders: tuple[Order, ...],
        book: IntentBook,
        equity_units: int,
    ) -> None:
        self.session: date = data.sessions[index]
        self.symbols = data.symbols
        self.account = account
        self.orders = orders
        self.intents: tuple[IntentRecord, ...] = tuple(item.record() for item in book.history)
        self._data, self._index, self._history = data, index, history
        self._book, self._equity = book, equity_units
        self._active = True

    def history(
        self, symbol: str, *, bars: int | None = None, field: str = "close"
    ) -> NDArray[np.float64]:
        self._symbol(symbol)
        if field not in self._history:
            raise ValueError("history field must be open, high, low or close")
        if bars is not None:
            bars = integer(bars, 1, "bars", 1, 1_000_000_000)
        end = self._index + 1
        start = max(0, end - bars) if bars is not None else 0
        values = self._history[field][start:end, self.symbols.index(symbol)].copy()
        values.setflags(write=False)
        return values

    def order(self, symbol: str, quantity: int) -> int:
        """Signed fixed shares, attempted at the next open only."""
        self._ready(symbol)
        quantity = integer(quantity, 1, "quantity", -1_000_000_000, 1_000_000_000)
        if not quantity:
            raise ValueError("order quantity cannot be zero")
        return self._book.place(self.session, symbol, "order", quantity)

    def target_positions(self, quantities: Mapping[str, int]) -> tuple[int, ...]:
        """Persistent target shares for the supplied securities; omitted ones are unchanged."""
        for symbol, value in quantities.items():
            self._ready(symbol)
            integer(value, 1, "target quantity", 0, 1_000_000_000)
        return tuple(
            self._book.place(self.session, symbol, "target", int(value))
            for symbol, value in quantities.items()
        )

    def target_weights(
        self, weights: Mapping[str, Number], *, rebalance: bool = False
    ) -> tuple[int, ...]:
        """Set portfolio weights; unchanged weights keep their original fixed-share targets.

        Omitted securities target zero. Set rebalance=True for a new allocation even
        when the requested weights are unchanged. Fees may reduce actual fills.
        """
        if not isinstance(rebalance, bool):
            raise ValueError("rebalance must be boolean")
        for symbol in weights:
            self._ready(symbol)
        values = tuple(ratio(weights.get(symbol, 0), "weight") for symbol in self.symbols)
        if sum(values) > 1_000_000:
            raise ValueError("long-only target weights must sum to at most one")
        if not rebalance and values == self._book.last_weights:
            return ()
        quantities = {
            symbol: self._weight_quantity(symbol, weight)
            for symbol, weight in zip(self.symbols, values, strict=True)
        }
        ids = self.target_positions(quantities)
        self._book.last_weights = values
        return ids

    def cancel(self, intent_id: int) -> None:
        if not self._active:
            raise RuntimeError("orders can only be changed during their close callback")
        self._book.cancel(self.session, intent_id)

    def _weight_quantity(self, symbol: str, weight: int) -> int:
        if not weight:
            return 0
        column = self.symbols.index(symbol)
        bar = self._data.bars[self._index * len(self.symbols) + column]
        if bar.close <= 0:
            raise ValueError(f"cannot size a target without a current valuation: {symbol}")
        rule = self._data.rules.at(symbol, self.session).rule
        desired = self._equity * weight // 1_000_000 // bar.close
        position = self.account.positions[symbol]
        current = position.quantity + position.pending_quantity
        if desired > current:
            extra = desired - current
            extra = (
                0
                if extra < rule.buy_minimum
                else (
                    rule.buy_minimum + (extra - rule.buy_minimum) // rule.buy_step * rule.buy_step
                )
            )
            return current + extra
        reduction = (current - desired) // rule.sell_step * rule.sell_step
        if reduction < rule.sell_minimum:
            reduction = 0
        return current - reduction

    def _symbol(self, symbol: str) -> None:
        if symbol not in self.symbols:
            raise ValueError(f"unknown strategy symbol: {symbol}")

    def _ready(self, symbol: str) -> None:
        if not self._active:
            raise RuntimeError("orders can only be changed during their close callback")
        self._symbol(symbol)


def account_view(
    cash: int, equity: int, positions: list[Position], receivable: int = 0, tax_payable: int = 0
) -> AccountView:
    return AccountView(
        cash / 10_000,
        equity / 10_000,
        MappingProxyType({position.symbol: position for position in positions}),
        dividend_receivable=receivable / 10_000,
        tax_payable=tax_payable / 10_000,
    )
