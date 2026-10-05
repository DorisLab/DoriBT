"""Daily lifecycle orchestrator. Strategy callbacks never run inside JIT."""

from collections.abc import Callable, Mapping

import numpy as np

from .account import Account, Position
from .compiled import compile_data
from .context import Context, account_view
from .costs import Costs
from .data import MarketData
from .execution import BUY_STEP, MINIMUM, ORDER_MAXIMUM, SELL_STEP, IntArray, executor
from .intents import IntentBook
from .orders import REASONS, Order
from .provenance import RunInfo, bind_strategy, parameters_copy, run_info
from .result import BacktestResult
from .rights import RightsBook
from .targets import WeightTargets
from .validation import Number, amount


class Backtest:
    """Long-only daily cash account with ordinary domestic individual dividend tax.

    Decisions made at a session's close first execute at the next supplied open.
    Raw prices, rule periods and distribution facts belong to ``MarketData``.
    """

    def __init__(
        self, data: MarketData, *, initial_cash: Number = 100_000, costs: Costs | None = None
    ) -> None:
        self.data = data
        self._initial_cash = amount(initial_cash, "initial_cash")
        if not self._initial_cash:
            raise ValueError("initial_cash must be positive")
        self.costs = costs or Costs()

    @property
    def initial_cash(self) -> float:
        return self._initial_cash / 10_000

    def run(
        self,
        strategy: Callable[..., None],
        *,
        parameters: Mapping[str, object] | None = None,
        backend: str = "python",
    ) -> BacktestResult:
        if isinstance(strategy, WeightTargets):
            strategy.validate(self.data)
        values = parameters_copy(parameters)
        callback = bind_strategy(strategy, values)
        run = _Run(self.data, self._initial_cash, self.costs, backend)
        info = run_info(self.data, self._initial_cash, self.costs, strategy, values, backend)
        return run.execute(callback, info)


class _Run:
    def __init__(self, data: MarketData, initial_cash: int, costs: Costs, backend: str) -> None:
        self.data, self.initial_cash, self.backend = data, initial_cash, backend
        self.compiled, self.costs = compile_data(data), costs.compile()
        self.kernel = executor(backend)
        self.account = Account(initial_cash, data.symbols)
        self.book = IntentBook()
        self.rights = RightsBook(data)
        self.orders: list[Order] = []
        self.history = {field: data.prices(field) for field in ("open", "high", "low", "close")}
        days, columns = len(data.sessions), len(data.symbols)
        self.equity, self.cash = np.zeros(days, dtype=np.int64), np.zeros(days, dtype=np.int64)
        self.holdings = np.zeros((days, columns), dtype=np.int64)
        self.sellable = np.zeros((days, columns), dtype=np.int64)
        self.pending_shares = np.zeros((days, columns), dtype=np.int64)
        self.receivable, self.tax_payable = (
            np.zeros(days, dtype=np.int64),
            np.zeros(days, dtype=np.int64),
        )

    def execute(self, strategy: Callable[[Context], None], info: RunInfo) -> BacktestResult:
        for index, session in enumerate(self.data.sessions):
            self._open(index)
            self._close(index)
            positions = [
                Position(
                    symbol,
                    int(self.holdings[index, column]),
                    int(self.sellable[index, column]),
                    int(self.holdings[index, column] + self.pending_shares[index, column])
                    * int(self.compiled.closes[index, column])
                    / 10_000,
                    int(self.pending_shares[index, column]),
                )
                for column, symbol in enumerate(self.data.symbols)
            ]
            view = account_view(
                self.account.cash,
                int(self.equity[index]),
                positions,
                int(self.receivable[index]),
                int(self.tax_payable[index]),
            )
            context = Context(
                self.data,
                index,
                self.history,
                view,
                tuple(self.orders),
                self.book,
                int(self.equity[index]),
            )
            try:
                strategy(context)
            except Exception as error:
                raise RuntimeError(f"strategy failed at close on {session}: {error}") from error
            finally:
                context._active = False
        self.book.finish(self.data.sessions[-1])
        for array in (
            self.equity,
            self.cash,
            self.holdings,
            self.sellable,
            self.pending_shares,
            self.receivable,
            self.tax_payable,
            self.compiled.closes,
        ):
            array.setflags(write=False)
        return BacktestResult(
            self.data.sessions,
            self.data.symbols,
            self.initial_cash / 10_000,
            self.equity,
            self.cash,
            self.holdings,
            self.sellable,
            tuple(self.orders),
            tuple(item.record() for item in self.book.history),
            self.backend,
            self.data.fingerprint,
            self.pending_shares,
            self.receivable,
            self.tax_payable,
            self.rights.records(),
            tuple(self.rights.events),
            self.rights.tax.records(),
            self.rights.tax.lot_records(),
            tuple(self.rights.tax.payments),
            self.compiled.closes,
            info,
        )

    def _open(self, index: int) -> None:
        self.rights.start(index, self.account, self.book)
        positions, sellable = self.account.quantities(), self.account.quantities(index)
        positions = positions + self.rights.pending_shares()
        if np.any(positions > 1_000_000_000):
            raise OverflowError("economic share quantity exceeds supported bounds")
        requests = np.zeros(len(self.data.symbols), dtype=np.int64)
        for column, symbol in enumerate(self.data.symbols):
            if intent := self.book.pending.get(symbol):
                requests[column] = intent.quantity
                if intent.kind == "target":
                    requests[column] = self._target_request(
                        index, column, intent.quantity - int(positions[column])
                    )
                if not requests[column]:
                    intent.finish(self.data.sessions[index], "fulfilled")
                    del self.book.pending[symbol]
        cash, rows = self.kernel(
            self.account.cash,
            positions,
            sellable,
            requests,
            self.compiled.market[index],
            self.costs,
            self.rights.tax.payable,
        )
        # Record in actual execution order so replay uses sale proceeds for later buys.
        columns = sorted(range(len(requests)), key=lambda column: (requests[column] > 0, column))
        for column in columns:
            if requests[column]:
                self._record(index, column, int(requests[column]), rows[column])
        self.account.cash = self.rights.tax.settle(self.data.sessions[index], cash)

    def _record(self, index: int, column: int, requested: int, row: IntArray) -> None:
        symbol, session = self.data.symbols[column], self.data.sessions[index]
        intent = self.book.pending[symbol]
        fill, price, commission, stamp, transfer, reason = map(int, row)
        order = Order(
            len(self.orders) + 1,
            intent.intent_id,
            session,
            symbol,
            requested,
            fill,
            price,
            commission,
            stamp,
            transfer,
            REASONS[reason],
        )
        self.orders.append(order)
        self.account.apply(order, index, int(self.compiled.settlement[index, column]))
        completed = intent.kind == "order" or (
            int(self.account.quantities()[column] + self.rights.pending_shares()[column])
            == intent.quantity
        )
        if fill == requested and completed:
            intent.finish(session, "fulfilled")
        elif order.reason.value == "invalid_quantity":
            intent.finish(session, "rejected", order.reason.value)
        elif intent.kind == "order":
            intent.finish(session, "expired", order.reason.value)
        if intent.status != "active":
            del self.book.pending[symbol]

    def _target_request(self, index: int, column: int, quantity: int) -> int:
        rule = self.compiled.market[index, column]
        maximum = int(rule[ORDER_MAXIMUM])
        # Inactive rows have no rule; retain the request for an explicit market rejection.
        if not maximum or abs(quantity) <= maximum:
            return quantity
        if quantity < 0:
            return -(maximum // int(rule[SELL_STEP]) * int(rule[SELL_STEP]))
        minimum, step = int(rule[MINIMUM]), int(rule[BUY_STEP])
        size = minimum + (maximum - minimum) // step * step
        remainder = quantity - size
        if 0 < remainder < minimum:
            size -= (minimum - remainder + step - 1) // step * step
        # Preserve the original invalid request if no legal first child fits.
        return size if size >= minimum else quantity

    def _close(self, index: int) -> None:
        self.rights.close(index, self.account)
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
        self.sellable[index] = self.account.quantities(index)
