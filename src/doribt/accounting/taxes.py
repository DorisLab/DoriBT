"""Daily net-share tax lots for the ordinary domestic individual policy.

Sources and modeling dates are documented in docs/corporate-actions.md.
Transaction lots are intentionally not reused: credited bonus shares and sales
can offset in the account's daily net change.
"""

from calendar import monthrange
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from doribt.validation import MAX_MONEY

TAX_POLICY = "cn-individual-2015@2026-10-06"


def anniversary(acquired: date, months: int) -> date:
    ordinal = acquired.year * 12 + acquired.month - 1 + months
    year, month = divmod(ordinal, 12)
    month += 1
    return date(year, month, min(acquired.day, monthrange(year, month)[1]))


def dividend_rate(acquired: date, sold: date) -> int:
    if sold < acquired:
        raise ValueError("tax disposal cannot precede acquisition")
    if sold <= anniversary(acquired, 1):
        return 200_000
    if sold <= anniversary(acquired, 12):
        return 100_000
    return 0


def validate_tax_period(session: date) -> None:
    if not date(2015, 9, 9) <= session <= date(2026, 10, 6):
        raise ValueError("dividend tax date is outside the verified individual tax policy")


@dataclass
class TaxLot:
    lot_id: int
    symbol: str
    acquired: date
    quantity: int
    income_micros: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class TaxLotRecord:
    lot_id: int
    symbol: str
    acquired: date
    quantity: int
    income_micros: tuple[tuple[str, int], ...]


@dataclass
class Assessment:
    action_id: str
    symbol: str
    session: date
    amount_units: int
    paid_units: int = 0


@dataclass(frozen=True)
class TaxRecord:
    action_id: str
    symbol: str
    assessed: date
    amount_units: int
    paid_units: int


@dataclass(frozen=True)
class TaxPayment:
    action_id: str
    symbol: str
    session: date
    amount_units: int


class TaxBook:
    def __init__(self, kinds: Mapping[str, str]) -> None:
        self.kinds = dict(kinds)
        self.lots: list[TaxLot] = []
        self.assessments: list[Assessment] = []
        self.payments: list[TaxPayment] = []
        self._next_id = 1

    def reconcile(self, session: date, holdings: Mapping[str, int]) -> None:
        """Reconcile registered end-of-day shares, never individual trade fragments."""
        for symbol, current in holdings.items():
            previous = sum(lot.quantity for lot in self.lots if lot.symbol == symbol)
            change = current - previous
            if change > 0:
                self.lots.append(TaxLot(self._next_id, symbol, session, change))
                self._next_id += 1
            elif change < 0:
                self._dispose(symbol, -change, session)

    def attach(self, symbol: str, action_id: str, income_micros: int, session: date) -> None:
        if self.kinds[symbol] == "etf":
            return
        validate_tax_period(session)
        for lot in self.lots:
            if lot.symbol == symbol:
                lot.income_micros[action_id] = income_micros

    def _dispose(self, symbol: str, quantity: int, session: date) -> None:
        products: dict[str, int] = {}
        for lot in self.lots:
            if not quantity:
                break
            if lot.symbol != symbol:
                continue
            consumed = min(lot.quantity, quantity)
            if lot.income_micros:
                validate_tax_period(session)
            rate = dividend_rate(lot.acquired, session)
            for action_id, income in lot.income_micros.items():
                products[action_id] = products.get(action_id, 0) + consumed * income * rate
            lot.quantity -= consumed
            quantity -= consumed
        self.lots = [lot for lot in self.lots if lot.quantity]
        if quantity:
            raise RuntimeError("tax disposal exceeds registered shares")
        for action_id, product in products.items():
            # income is micro-yuan and the rate is ppm; round the aggregate to cents.
            tax = ((product + 5_000_000_000) // 10_000_000_000) * 100
            if tax > MAX_MONEY:
                raise OverflowError("dividend tax exceeds supported bounds")
            self.assessments.append(Assessment(action_id, symbol, session, tax))

    @property
    def payable(self) -> int:
        total = sum(item.amount_units - item.paid_units for item in self.assessments)
        if total > MAX_MONEY:
            raise OverflowError("dividend tax payable exceeds supported bounds")
        return total

    def settle(self, session: date, cash: int) -> int:
        for item in self.assessments:
            if item.session >= session:
                continue
            payment = min(cash, item.amount_units - item.paid_units)
            if payment:
                cash -= payment
                item.paid_units += payment
                self.payments.append(TaxPayment(item.action_id, item.symbol, session, payment))
        return cash

    def records(self) -> tuple[TaxRecord, ...]:
        return tuple(
            TaxRecord(a.action_id, a.symbol, a.session, a.amount_units, a.paid_units)
            for a in self.assessments
        )

    def lot_records(self) -> tuple[TaxLotRecord, ...]:
        return tuple(
            TaxLotRecord(
                lot.lot_id,
                lot.symbol,
                lot.acquired,
                lot.quantity,
                tuple(sorted(lot.income_micros.items())),
            )
            for lot in self.lots
        )
