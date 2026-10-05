"""Single shared-account output; securities are named columns, never parameter runs."""

from dataclasses import dataclass
from datetime import date
from functools import cached_property

import numpy as np
from numpy.typing import NDArray

from .execution import IntArray
from .orders import Fill, IntentRecord, Order
from .rights import CorporateEvent, EntitlementRecord
from .taxes import TAX_POLICY, TaxLotRecord, TaxPayment, TaxRecord


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
    tax_policy: str = TAX_POLICY

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
        executed = (order for order in self.orders if order.filled)
        return tuple(Fill.from_order(index, order) for index, order in enumerate(executed, start=1))

    @property
    def total_return(self) -> float:
        return float(self.equity[-1] / self.initial_cash - 1)

    @property
    def max_drawdown(self) -> float:
        curve = np.r_[self.initial_cash, self.equity]
        return float(np.max(1 - curve / np.maximum.accumulate(curve)))

    def stats(self) -> dict[str, float | int]:
        return {
            "total_return": self.total_return,
            "max_drawdown": self.max_drawdown,
            "final_equity": float(self.equity[-1]),
            "fill_count": len(self.fills),
            "total_fees": sum(fill.fees for fill in self.fills),
            "dividend_tax": sum(tax.amount_units for tax in self.taxes) / 10_000,
        }
