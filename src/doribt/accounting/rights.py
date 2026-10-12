"""Record-date ownership, receivables, share credit and subsequent availability."""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date
from heapq import heappop, heappush

import numpy as np

from doribt.accounting.account import Account, Lot
from doribt.accounting.taxes import TaxBook
from doribt.kernels.execution import IntArray
from doribt.market.actions import CorporateAction
from doribt.market.data import MarketData
from doribt.runtime.intents import IntentBook
from doribt.validation import MAX_MONEY, day, integer


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
        self._columns = {symbol: column for column, symbol in enumerate(data.symbols)}
        self._pending = dict.fromkeys(data.symbols, 0)
        self._receivable = 0
        self._outstanding: dict[str, int] = {}
        self._settlement_events: list[tuple[date, int, str]] = []
        self._due: set[str] = set()
        self._ranks: dict[str, int] = {}
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
        self._settle_due(index, account)
        account.cash = self.tax.settle(session, account.cash)

    def _settle_due(self, index: int, account: Account) -> None:
        session = self.data.sessions[index]
        while self._settlement_events and self._settlement_events[0][0] <= session:
            self._due.add(heappop(self._settlement_events)[2])
        # 到期日不同的事件仍按登记顺序处理，保持付款和股份记录顺序。
        for action_id in sorted(self._due, key=self._ranks.__getitem__):
            entitlement = self.entitlements[action_id]
            outstanding = not entitlement.cash_paid or not entitlement.shares_credited
            self._pay(entitlement, session, account)
            self._credit(entitlement, index, account)
            if outstanding and entitlement.cash_paid and entitlement.shares_credited:
                self._outstanding[entitlement.action.symbol] -= 1
            self._due.remove(action_id)

    def _schedule(self, entitlement: Entitlement) -> None:
        action = entitlement.action
        if not entitlement.cash_paid:
            self._receivable += entitlement.cash_units
        if not entitlement.shares_credited:
            self._pending[action.symbol] += entitlement.bonus_quantity
        if not entitlement.cash_paid or not entitlement.shares_credited:
            self._outstanding[action.symbol] = self._outstanding.get(action.symbol, 0) + 1
        dates = {action.pay_date, action.share_credit_date} - {None}
        for when in dates:
            if when is not None:
                heappush(
                    self._settlement_events,
                    (day(when), self._ranks[action.action_id], action.action_id),
                )

    def close(self, index: int, account: Account) -> None:
        session = self.data.sessions[index]
        quantities = account.quantities()
        # 仍按证券顺序对日末净变化记税务批次；日内往返不能生成额外批次。
        changed = {
            symbol: int(quantities[column])
            for column, symbol in enumerate(self.data.symbols)
            if symbol in account.changed_symbols
        }
        self.tax.reconcile(session, changed)
        account.changed_symbols.clear()
        for action in self._record.get(session, []):
            quantity = int(quantities[account._columns[action.symbol]])
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
        self._ranks.setdefault(action.action_id, len(self.entitlements))
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
        held = int(account.quantities()[self._columns[action.symbol]])
        pending = bool(self._outstanding.get(action.symbol, 0))
        if action.kind != "distribution" and (entitlement is not None or held or pending):
            raise UnsupportedCorporateAction(f"unsupported {action.kind}: {action.action_id}")
        if entitlement is not None:
            if not entitlement.accrued:
                self._schedule(entitlement)
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
        self._receivable -= entitlement.cash_units
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
        account.add_lot(
            Lot(
                action.symbol,
                entitlement.bonus_quantity,
                day(action.share_credit_date),
                available,
                0,
            )
        )
        entitlement.shares_credited = True
        self._pending[action.symbol] -= entitlement.bonus_quantity
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
        total = self._receivable
        if total > MAX_MONEY:
            raise OverflowError("dividend receivables exceed supported bounds")
        return total

    def pending_shares(self) -> IntArray:
        if any(quantity > 1_000_000_000 for quantity in self._pending.values()):
            raise OverflowError("pending share quantity exceeds supported bounds")
        return np.array(list(self._pending.values()), dtype=np.int64)

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
