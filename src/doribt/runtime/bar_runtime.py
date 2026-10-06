"""Bar execution shares the formal account, corporate-action and result lifecycle."""

from collections.abc import Callable
from dataclasses import replace
from types import MappingProxyType

import numpy as np

from doribt.accounting.costs import Costs
from doribt.kernels.compiled import PreparedData
from doribt.provenance import RunInfo
from doribt.reporting.result import BacktestResult
from doribt.runtime.bar_targets import BarIntentBook
from doribt.runtime.broker import Broker
from doribt.runtime.context import Context
from doribt.runtime.engine import _Run
from doribt.runtime.matching import matcher
from doribt.runtime.slippage import BarExecution


class BarRun(_Run):
    def __init__(
        self,
        prepared: PreparedData,
        initial_cash: int,
        costs: Costs,
        backend: str,
        execution: BarExecution,
    ) -> None:
        super().__init__(prepared, initial_cash, costs, backend)
        self.broker = Broker(
            self.data,
            self.compiled,
            self.account,
            self.costs,
            execution.compile(),
            matcher(backend),
        )
        self.targets = BarIntentBook(self.broker)
        self.book = self.targets
        self.reserved_cash = np.zeros_like(self.cash)
        self.reserved_shares = np.zeros_like(self.holdings)

    def _open(self, index: int) -> None:
        day_index = self.data.day_index(index)
        self.broker.index = index
        if index == 0 or self.data.day_index(index - 1) != day_index:
            self.rights.start(day_index, self.account, self.book)
        self.broker.tax = self.rights.tax.payable
        if index:
            pending = dict(
                zip(self.data.symbols, map(int, self.rights.pending_shares()), strict=True)
            )
            self.targets.sync(index, pending)
        self.broker.advance(index)

    def _close(self, index: int) -> None:
        day_index = self.data.day_index(index)
        final = index + 1 == len(self.data.timeline) or self.data.day_index(index + 1) != day_index
        if final:
            self.broker.end_day()
            self.rights.close(day_index, self.account)
        self.broker.tax = self.rights.tax.payable
        self.pending_shares[index] = self.rights.pending_shares()
        self.receivable[index], self.tax_payable[index] = (
            self.rights.receivable,
            self.rights.tax.payable,
        )
        self.equity[index] = self.account.value(
            self.compiled.closes[index],
            self.pending_shares[index],
            int(self.receivable[index]),
            int(self.tax_payable[index]),
        )
        self.cash[index] = self.account.cash
        self.holdings[index] = self.account.quantities()
        self.sellable[index] = self.account.quantities(day_index)
        self.reserved_cash[index] = self.broker.frozen_cash
        self.reserved_shares[index] = [
            self.broker.frozen_shares(i) for i in range(len(self.data.symbols))
        ]

    def _context(self, index: int) -> Context:
        context = super()._context(index)
        context._order_reader = lambda: tuple(self.broker.orders)
        context._submit = self.broker.submit
        context._cancel_order = self.broker.cancel
        positions = {
            symbol: replace(position, frozen_quantity=int(self.reserved_shares[index, i]))
            for i, (symbol, position) in enumerate(context.account.positions.items())
        }
        context.account = replace(
            context.account,
            frozen_cash=self.broker.frozen_cash / 10_000,
            positions=MappingProxyType(positions),
        )
        return context

    def _finish(self) -> None:
        quantities = self.account.quantities() + self.rights.pending_shares()
        for symbol, intent in tuple(self.book.pending.items()):
            if intent.quantity == quantities[self.data.symbols.index(symbol)]:
                intent.finish(self.data.sessions[-1], "fulfilled")
                del self.book.pending[symbol]
        self.broker.finish_all()
        self.orders = self.broker.orders
        super()._finish()

    def execute(self, strategy: Callable[[Context], None], info: RunInfo) -> BacktestResult:
        result = super().execute(strategy, info)
        self.reserved_cash.setflags(write=False)
        self.reserved_shares.setflags(write=False)
        return replace(
            result,
            executions=tuple(self.broker.fills),
            reserved_cash_units=self.reserved_cash,
            reserved_shares=self.reserved_shares,
        )
