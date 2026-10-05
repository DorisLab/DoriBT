"""Record-date ownership, receivables, share credit and subsequent availability."""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date

import numpy as np

from .account import Account, Lot
from .actions import CorporateAction
from .data import MarketData
from .execution import IntArray
from .intents import IntentBook
from .taxes import TaxBook
from .validation import MAX_MONEY, day, integer


class UnsupportedCorporateAction(ValueError):
    pass


@dataclass(frozen=True)
class CorporateEvent:
    session: date
    action_id: str
    symbol: str
    kind: str
    quantity: int = 0
    amount_units: int = 0


@dataclass
class Entitlement:
    action: CorporateAction
    quantity: int
    cash_units: int
    bonus_quantity: int
    accrued: bool = False
    cash_paid: bool = False
    shares_credited: bool = False


@dataclass(frozen=True)
class EntitlementRecord:
    action_id: str
    symbol: str
    record_date: date
    ex_date: date
    pay_date: date | None
    share_credit_date: date | None
    share_listing_date: date | None
    eligible_quantity: int
    cash_units: int
    bonus_quantity: int
    accrued: bool
    cash_paid: bool
    shares_credited: bool


class RightsBook:
    def __init__(self, data: MarketData) -> None:
        self.data = data
        self.kinds = {item.symbol: item.kind for item in data.instruments}
        self.tax = TaxBook(self.kinds)
        self.entitlements: dict[str, Entitlement] = {}
        self.events: list[CorporateEvent] = []
        self._record: dict[date, list[CorporateAction]] = {}
        self._ex: dict[date, list[CorporateAction]] = {}
        for action in data.actions:
            self._record.setdefault(day(action.record_date), []).append(action)
            self._ex.setdefault(day(action.ex_date), []).append(action)

    def start(self, index: int, account: Account, intents: IntentBook) -> None:
        session = self.data.sessions[index]
        for action in self._ex.get(session, []):
            if action.kind != "distribution" and action.symbol in intents.pending:
                raise UnsupportedCorporateAction(f"unsupported {action.kind}: {action.action_id}")
            self._ex_date(action, session, account)
            bonus = integer(action.bonus_per_share, 1_000_000, "bonus", 0, 100_000_000)
            intents.adjust(action.symbol, action.action_id, session, bonus)
        for entitlement in self.entitlements.values():
            if not entitlement.accrued:
                continue
            self._pay(entitlement, session, account)
            self._credit(entitlement, index, account)
        account.cash = self.tax.settle(session, account.cash)

    def close(self, index: int, account: Account) -> None:
        session = self.data.sessions[index]
        quantities = dict(zip(self.data.symbols, map(int, account.quantities()), strict=True))
        self.tax.reconcile(session, quantities)
        for action in self._record.get(session, []):
            quantity = quantities[action.symbol]
            if quantity:
                self._capture(action, quantity, session)

    def _capture(self, action: CorporateAction, quantity: int, session: date) -> None:
        cash_micros = integer(action.cash_per_share, 1_000_000, "cash per share", 0, MAX_MONEY)
        bonus = integer(action.bonus_per_share, 1_000_000, "bonus per share", 0, 100_000_000)
        if quantity * bonus % 1_000_000:
            raise UnsupportedCorporateAction(
                f"fractional share allocation unavailable: {action.action_id}"
            )
        cash = (quantity * cash_micros + 5000) // 10_000 * 100
        if cash > MAX_MONEY:
            raise OverflowError("dividend entitlement exceeds supported bounds")
        entitlement = Entitlement(
            action,
            quantity,
            cash,
            quantity * bonus // 1_000_000,
            cash_paid=not bool(cash),
            shares_credited=not bool(bonus),
        )
        self.entitlements[action.action_id] = entitlement
        if action.kind == "distribution":
            taxable_bonus = self._taxable_bonus(action, bonus)
            self.tax.attach(action.symbol, action.action_id, cash_micros + taxable_bonus, session)
        self.events.append(
            CorporateEvent(session, action.action_id, action.symbol, "recorded", quantity)
        )

    def _taxable_bonus(self, action: CorporateAction, bonus: int) -> int:
        value = action.taxable_bonus_amount_per_share
        if bonus and value is None and self.kinds[action.symbol] == "stock":
            raise ValueError(f"taxable bonus amount is required: {action.action_id}")
        return integer(value or 0, 1_000_000, "taxable bonus", 0, MAX_MONEY)

    def _ex_date(self, action: CorporateAction, session: date, account: Account) -> None:
        entitlement = self.entitlements.get(action.action_id)
        held = int(account.quantities()[self.data.symbols.index(action.symbol)])
        pending = any(
            e.action.symbol == action.symbol
            and e.accrued
            and (not e.shares_credited or not e.cash_paid)
            for e in self.entitlements.values()
        )
        if action.kind != "distribution" and (entitlement is not None or held or pending):
            raise UnsupportedCorporateAction(f"unsupported {action.kind}: {action.action_id}")
        if entitlement is not None:
            entitlement.accrued = True
            self.events.append(
                CorporateEvent(
                    session,
                    action.action_id,
                    action.symbol,
                    "accrued",
                    entitlement.bonus_quantity,
                    entitlement.cash_units,
                )
            )

    def _pay(self, entitlement: Entitlement, session: date, account: Account) -> None:
        action = entitlement.action
        if entitlement.cash_paid or action.pay_date is None or session < day(action.pay_date):
            return
        account.cash += entitlement.cash_units
        if account.cash > MAX_MONEY:
            raise OverflowError("dividend payment exceeds supported cash bounds")
        entitlement.cash_paid = True
        self.events.append(
            CorporateEvent(
                session,
                action.action_id,
                action.symbol,
                "cash_paid",
                amount_units=entitlement.cash_units,
            )
        )

    def _credit(self, entitlement: Entitlement, index: int, account: Account) -> None:
        action, session = entitlement.action, self.data.sessions[index]
        if entitlement.shares_credited or action.share_credit_date is None:
            return
        if session < day(action.share_credit_date):
            return
        if action.share_listing_date is None:
            raise RuntimeError("validated bonus shares require a listing date")
        available = bisect_left(self.data.sessions, day(action.share_listing_date))
        account.lots.append(
            Lot(
                action.symbol,
                entitlement.bonus_quantity,
                day(action.share_credit_date),
                available,
                0,
            )
        )
        entitlement.shares_credited = True
        self.events.append(
            CorporateEvent(
                session,
                action.action_id,
                action.symbol,
                "shares_credited",
                entitlement.bonus_quantity,
            )
        )

    @property
    def receivable(self) -> int:
        total = sum(
            e.cash_units for e in self.entitlements.values() if e.accrued and not e.cash_paid
        )
        if total > MAX_MONEY:
            raise OverflowError("dividend receivables exceed supported bounds")
        return total

    def pending_shares(self) -> IntArray:
        pending = dict.fromkeys(self.data.symbols, 0)
        for entitlement in self.entitlements.values():
            if entitlement.accrued and not entitlement.shares_credited:
                pending[entitlement.action.symbol] += entitlement.bonus_quantity
        if any(quantity > 1_000_000_000 for quantity in pending.values()):
            raise OverflowError("pending share quantity exceeds supported bounds")
        return np.array(list(pending.values()), dtype=np.int64)

    def records(self) -> tuple[EntitlementRecord, ...]:
        result = []
        for e in self.entitlements.values():
            action = e.action
            result.append(
                EntitlementRecord(
                    action.action_id,
                    action.symbol,
                    day(action.record_date),
                    day(action.ex_date),
                    None if action.pay_date is None else day(action.pay_date),
                    None if action.share_credit_date is None else day(action.share_credit_date),
                    None if action.share_listing_date is None else day(action.share_listing_date),
                    e.quantity,
                    e.cash_units,
                    e.bonus_quantity,
                    e.accrued,
                    e.cash_paid,
                    e.shares_credited,
                )
            )
        return tuple(result)
