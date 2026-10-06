"""Public close callback with a time-limited history and immutable account view."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

import numpy as np
from numpy.typing import NDArray

from doribt.accounting.account import Position
from doribt.accounting.orders import IntentRecord, Order
from doribt.market.adjustments import adjust
from doribt.market.data import MarketData
from doribt.research.outputs import Recorder
from doribt.runtime.intents import IntentBook
from doribt.runtime.sizing import validate_sizing, weight_quantity
from doribt.validation import Number, integer, ratio


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
        return max(0.0, self.cash - self.tax_payable - self.frozen_cash)


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
        self.session: date = data.sessions[data.day_index(index)]
        self.now: date = data.timeline[index]
        self.symbols = data.symbols
        self.account = account
        self._orders = orders
        self._intents: tuple[IntentRecord, ...] | None = None
        self._order_reader: Callable[[], tuple[Order, ...]] | None = None
        self._submit: Callable[[str, int, str, Number | None, Number | None], int] | None = None
        self._cancel_order: Callable[[int], None] | None = None
        self._data, self._index, self._history = data, index, history
        self._book, self._equity = book, equity_units
        self._active = True
        self._recorder: Recorder | None = None

    def record(self, **values: float | int | None) -> None:
        """Record finite named values at this close; omitted bars remain null."""
        if not self._active or self._recorder is None:
            raise RuntimeError("record requires an active strategy callback")
        self._recorder.record(self._index, values)

    @property
    def orders(self) -> tuple[Order, ...]:
        if self._order_reader is not None:
            if not self._active:
                raise RuntimeError("read order snapshots during the callback")
            return self._order_reader()
        return self._orders

    @property
    def intents(self) -> tuple[IntentRecord, ...]:
        if self._intents is None:
            if not self._active:
                raise RuntimeError("read intent snapshots during the callback")
            self._intents = tuple(item.record() for item in self._book.history)
        return self._intents

    @property
    def bar_index(self) -> int:
        """Zero-based position in the supplied calendar, including suspended sessions."""
        return self._index

    def history(
        self, symbol: str, *, bars: int | None = None, field: str = "close", adjustment: str = "raw"
    ) -> NDArray[np.float64]:
        self._symbol(symbol)
        if field not in self._history:
            raise ValueError("history field must be open, high, low or close")
        if adjustment not in {"raw", "asof"}:
            raise ValueError("adjustment must be 'raw' or 'asof'")
        if bars is not None:
            bars = integer(bars, 1, "bars", 1, 1_000_000_000)
        end = self._index + 1
        start = max(0, end - bars) if bars is not None else 0
        values = self._history[field][start:end, self.symbols.index(symbol)].copy()
        if adjustment == "asof":
            adjust(self._data, values.reshape(-1, 1), start=start, end=end, symbols=(symbol,))
        values.setflags(write=False)
        return values

    def order(
        self,
        symbol: str,
        quantity: int,
        *,
        valid_for: str = "next_bar",
        limit_price: Number | None = None,
        max_spend: Number | None = None,
    ) -> int:
        """固定股数委托；max_spend 是买单含费用的累计支出上限（元）。"""
        self._ready(symbol)
        quantity = integer(quantity, 1, "quantity", -1_000_000_000, 1_000_000_000)
        if not quantity:
            raise ValueError("order quantity cannot be zero")
        if self._submit is not None:
            return self._submit(symbol, quantity, valid_for, limit_price, max_spend)
        if valid_for != "next_bar" or limit_price is not None or max_spend is not None:
            raise ValueError("order lifetime, limit price and max_spend require BarExecution")
        return self._book.place(self.session, symbol, "order", quantity)

    def cancel_order(self, order_id: int) -> None:
        if not self._active or self._cancel_order is None:
            raise RuntimeError("cancel_order requires an active BarExecution callback")
        self._cancel_order(order_id)

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
        self, weights: Mapping[str, Number], *, rebalance: bool = False, sizing: str = "close"
    ) -> tuple[int, ...]:
        """按收盘或下一 bar 开盘定量一次；相同权重和模式保留原股数。

        sizing='execution' 使用成交前的开盘权益和原始开盘价，不扣预计费用。
        rebalance=True 重新定量，省略证券为零；费用及交易约束可能减少成交。
        """
        if not isinstance(rebalance, bool):
            raise ValueError("rebalance must be boolean")
        validate_sizing(sizing)
        if sizing == "execution" and self._submit is None:
            raise ValueError("execution sizing requires BarExecution")
        for symbol in self.symbols + tuple(weights):
            self._ready(symbol)
        values = tuple(ratio(weights.get(symbol, 0), "weight") for symbol in self.symbols)
        if sum(values) > 1_000_000:
            raise ValueError("long-only target weights must sum to at most one")
        if not rebalance and (sizing, values) == self._book.last_weights:
            return ()
        quantities = {
            symbol: self._weight_quantity(symbol, weight) if sizing == "close" else 0
            for symbol, weight in zip(self.symbols, values, strict=True)
        }
        ids = tuple(
            self._book.place_weight(
                self.session,
                symbol,
                weight,
                sizing,
                quantities[symbol],
                self.now if sizing == "close" else None,
            )
            for symbol, weight in zip(self.symbols, values, strict=True)
        )
        self._book.last_weights = (sizing, values)
        return ids

    def cancel(self, intent_id: int) -> None:
        if not self._active:
            raise RuntimeError("orders can only be changed during their close callback")
        self._book.cancel(self.session, intent_id)

    def _weight_quantity(self, symbol: str, weight: int) -> int:
        column = self.symbols.index(symbol)
        bar = self._data.bars[self._index * len(self.symbols) + column]
        if not weight:
            return 0
        rule = self._data.rules.at(symbol, self.session).rule
        position = self.account.positions[symbol]
        current = position.quantity + position.pending_quantity
        return weight_quantity(self._equity, weight, bar.close, current, rule)

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
