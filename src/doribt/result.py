"""Single shared-account output; securities are named columns, never parameter runs."""

from dataclasses import dataclass
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from .analysis import Statistics, drawdown, returns, statistics
from .benchmark import Benchmark
from .execution import IntArray
from .orders import Fill, IntentRecord, Order
from .provenance import RunInfo
from .rights import CorporateEvent, EntitlementRecord
from .taxes import TAX_POLICY, TaxLotRecord, TaxPayment, TaxRecord

if TYPE_CHECKING:
    from matplotlib.figure import Figure


@dataclass(frozen=True)
class BacktestResult:
    sessions: tuple[date, ...]
    symbols: tuple[str, ...]
    initial_cash: float
    equity_units: IntArray
    cash_units: IntArray
    holdings: IntArray
    sellable: IntArray
    orders: tuple[Order, ...]
    intents: tuple[IntentRecord, ...]
    backend: str
    data_fingerprint: str
    pending_shares: IntArray
    dividend_receivable_units: IntArray
    tax_payable_units: IntArray
    entitlements: tuple[EntitlementRecord, ...]
    corporate_events: tuple[CorporateEvent, ...]
    taxes: tuple[TaxRecord, ...]
    tax_lots: tuple[TaxLotRecord, ...]
    tax_payments: tuple[TaxPayment, ...]
    close_units: IntArray
    run_info: RunInfo
    tax_policy: str = TAX_POLICY
    executions: tuple[Fill, ...] | None = None
    reserved_cash_units: IntArray | None = None
    reserved_shares: IntArray | None = None

    @cached_property
    def frozen_cash_units(self) -> IntArray:
        return (
            np.zeros_like(self.cash_units)
            if self.reserved_cash_units is None
            else self.reserved_cash_units
        )

    @cached_property
    def frozen_shares(self) -> IntArray:
        return (
            np.zeros_like(self.holdings) if self.reserved_shares is None else self.reserved_shares
        )

    @property
    def equity(self) -> NDArray[np.float64]:
        return self.equity_units / 10_000

    @property
    def cash(self) -> NDArray[np.float64]:
        return self.cash_units / 10_000

    @property
    def dividend_receivable(self) -> NDArray[np.float64]:
        return self.dividend_receivable_units / 10_000

    @property
    def tax_payable(self) -> NDArray[np.float64]:
        return self.tax_payable_units / 10_000

    @cached_property
    def fills(self) -> tuple[Fill, ...]:
        if self.executions is not None:
            return self.executions
        executed = (order for order in self.orders if order.filled)
        return tuple(Fill.from_order(index, order) for index, order in enumerate(executed, start=1))

    @property
    def total_return(self) -> float:
        return float(self.equity[-1] / self.initial_cash - 1)

    @property
    def max_drawdown(self) -> float:
        return float(np.max(self.drawdown))

    @property
    def nav(self) -> NDArray[np.float64]:
        return self.equity / self.initial_cash

    @property
    def returns(self) -> NDArray[np.float64]:
        return returns(self.equity)

    @property
    def drawdown(self) -> NDArray[np.float64]:
        return drawdown(self.equity, self.initial_cash)

    def stats(
        self,
        *,
        benchmark: Benchmark | None = None,
        periods_per_year: float | None = None,
        risk_free_rate: float = 0.0,
    ) -> Statistics:
        return statistics(
            self,
            benchmark=benchmark,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
        )

    def plot(self, *, benchmark: Benchmark | None = None) -> "Figure":
        """Return a Matplotlib Figure without opening a GUI or changing its backend."""
        from .plotting import plot

        return plot(self, benchmark)

    def export(
        self,
        path: str | Path,
        *,
        benchmark: Benchmark | None = None,
        periods_per_year: float | None = None,
        risk_free_rate: float = 0.0,
        plot: bool = False,
    ) -> Path:
        """Publish JSON/CSV and optional PNG to a new directory; never overwrite."""
        from .export import export

        return export(
            self,
            Path(path),
            benchmark=benchmark,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
            include_plot=plot,
        )
