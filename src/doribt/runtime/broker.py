"""Order lifetime, reservations and immutable fill records around the numeric matcher."""

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from doribt.accounting.account import Account
from doribt.accounting.orders import REASONS, Fill, Order, Reason
from doribt.kernels.compiled import CompiledData
from doribt.kernels.execution import (
    BUY_STEP,
    MINIMUM,
    ODD_LOT,
    OPEN,
    ORDER_MAXIMUM,
    SELL_MINIMUM,
    SELL_STEP,
    TICK,
    IntArray,
)
from doribt.kernels.reservation import reservation
from doribt.market.data import MarketData
from doribt.runtime.matching import (
    BUDGET,
    LEFT,
    LIMIT,
    NOTIONAL,
    PAID,
    RESERVED,
    Matcher,
)
from doribt.runtime.order_state import OrderState
from doribt.validation import MAX_MONEY, Number, amount


@dataclass(slots=True)
class PendingOrder:
    order_id: int
    column: int
    submitted: int
    activation_day: int
    values: IntArray
    spend_left: int = MAX_MONEY
    buying: bool = True


def submission_reason(quantity: int, position: int, rule: IntArray) -> Reason:
    size = abs(quantity)
    if size > rule[ORDER_MAXIMUM] or not rule[TICK]:
        return Reason.INVALID_QUANTITY
    if quantity > 0:
        valid = size >= rule[MINIMUM] and (size - rule[MINIMUM]) % rule[BUY_STEP] == 0
    else:
        valid = size >= rule[SELL_MINIMUM] and size % rule[SELL_STEP] == 0
        valid = valid or bool(rule[ODD_LOT] and size == position)
    return Reason.NONE if valid else Reason.INVALID_QUANTITY


class Broker:
    def __init__(
        self,
        data: MarketData,
        compiled: CompiledData,
        account: Account,
        costs: IntArray,
        config: IntArray,
        kernel: Matcher,
        backend: str = "python",
    ) -> None:
        self.data, self.compiled, self.account = data, compiled, account
        self.costs, self.config, self.kernel = costs, config, kernel
        self.reserve_cost = reservation(backend)
        self._orders: list[OrderState] = []
        self._snapshots: list[Order] = []
        self._dirty_orders: set[int] = set()
        self.fills: list[Fill] = []
        self.active: dict[int, PendingOrder] = {}
        self.index = 0
        self.tax = 0
        self._frozen_cash = 0
        self._frozen_shares = [0] * len(data.symbols)
        self._columns = {symbol: column for column, symbol in enumerate(data.symbols)}

    @property
    def orders(self) -> list[Order]:
        for index in sorted(self._dirty_orders):
            snapshot = self._orders[index].snapshot()
            if index == len(self._snapshots):
                self._snapshots.append(snapshot)
            else:
                self._snapshots[index] = snapshot
        self._dirty_orders.clear()
        return self._snapshots

    @property
    def frozen_cash(self) -> int:
        return self._frozen_cash

    def frozen_shares(self, column: int) -> int:
        return self._frozen_shares[column]

    def _reservations(self, item: PendingOrder, cash: int, shares: int) -> None:
        self._frozen_cash += cash - int(item.values[BUDGET])
        self._frozen_shares[item.column] += shares - int(item.values[RESERVED])
        item.values[BUDGET], item.values[RESERVED] = cash, shares

    def submit(
        self,
        symbol: str,
        quantity: int,
        valid_for: str = "next_bar",
        limit_price: Number | None = None,
        max_spend: Number | None = None,
        *,
        intent_id: int = 0,
        sizing_index: int | None = None,
    ) -> int:
        if valid_for not in {"next_bar", "day"}:
            raise ValueError("valid_for must be next_bar or day")
        column, index = self._columns[symbol], self.index
        rule = self.compiled.market[index if sizing_index is None else sizing_index, column]
        limit = 0 if limit_price is None else amount(limit_price, "limit_price")
        if limit_price is not None and (limit <= 0 or not rule[TICK] or limit % rule[TICK]):
            raise ValueError("limit_price must be positive and on tick")
        ceiling = None if max_spend is None else amount(max_spend, "max_spend")
        if ceiling is not None and (ceiling <= 0 or quantity < 0):
            raise ValueError("max_spend must be positive and only applies to buy orders")
        position = int(self.account.quantities()[column])
        reason = submission_reason(quantity, position, rule)
        state = "accepted" if reason == Reason.NONE else "rejected"
        order_id = len(self._orders) + 1
        now, session = self.data.timeline[index], self.data.sessions[self.data.day_index(index)]
        self._orders.append(
            OrderState(
                order_id,
                intent_id,
                session,
                symbol,
                quantity,
                0,
                0,
                0,
                0,
                0,
                reason,
                now,
                now,
                state,
                valid_for=valid_for,
                limit_units=limit,
                max_spend_units=ceiling,
            )
        )
        self._dirty_orders.add(order_id - 1)
        if state == "accepted":
            next_index = min(index + 1, len(self.data.timeline) - 1)
            values = np.array([quantity, 0, 0, 0, 0, limit], dtype=np.int64)
            item = PendingOrder(
                order_id,
                column,
                index,
                self.data.day_index(next_index),
                values,
                MAX_MONEY if ceiling is None else ceiling,
                quantity > 0,
            )
            self.active[order_id] = item
            self._reserve(item, sizing_index)
        return order_id

    def _reserve(self, item: PendingOrder, sizing_index: int | None = None) -> None:
        values, index, column = item.values, self.index, item.column
        if not item.buying:
            available = int(self.account.quantities(self.data.day_index(index))[column])
            reserved = min(-int(values[LEFT]), max(0, available - self.frozen_shares(column)))
            self._reservations(item, int(values[BUDGET]), reserved)
        else:
            cost = self.reserve_cost(
                self.compiled.market[index if sizing_index is None else sizing_index, column],
                self.config,
                self.costs,
                int(values[LEFT]),
                int(values[LIMIT]),
                int(self.compiled.closes[index, column]),
                sizing_index is not None,
            )
            available = max(0, self.account.cash - self.tax - self.frozen_cash)
            self._reservations(item, min(available, cost, item.spend_left), int(values[RESERVED]))
        self._snapshot(item)

    def match_state(self, item: PendingOrder) -> IntArray:
        """预留估值保护其他挂单；可支出金额还包括当前未占用现金。"""
        if not item.buying:
            return item.values
        state = item.values.copy()
        state[BUDGET] = min(self.available_cash(item), item.spend_left)
        return state

    def available_cash(self, item: PendingOrder) -> int:
        return max(0, self.account.cash - self.tax - self.frozen_cash + int(item.values[BUDGET]))

    def cancel(self, order_id: int) -> None:
        if order_id not in self.active:
            raise ValueError(f"no active order {order_id}")
        self.finish(order_id, "cancelled")

    def finish(self, order_id: int, state: str) -> None:
        item = self.active.pop(order_id)
        self._reservations(item, 0, 0)
        self._snapshot(item, state)

    def _snapshot(self, item: PendingOrder, state: str | None = None) -> None:
        order = self._orders[item.order_id - 1]
        order.updated_at = self.data.timeline[self.index]
        order.state = state or order.state
        order.frozen_cash_units = int(item.values[BUDGET])
        order.frozen_quantity = int(item.values[RESERVED])
        self._dirty_orders.add(item.order_id - 1)

    def advance(self, index: int) -> None:
        self.index = index
        used = np.zeros(len(self.data.symbols), dtype=np.int64)
        # dict 保留递增订单号的插入顺序；稳定排序只需卖出优先标记。
        queue = sorted(self.active.values(), key=lambda item: item.buying)
        for item in queue:
            if item.submitted < index:
                self._attempt(item, used)

    def _attempt(self, item: PendingOrder, used: IntArray) -> None:
        index, column = self.index, item.column
        order = self._orders[item.order_id - 1]
        bar = self.data.bars[index * len(self.data.symbols) + column]
        if not item.buying:
            # Newly settled shares may fund an order submitted at yesterday's final close.
            self._reservations(item, int(item.values[BUDGET]), 0)
            self._reserve(item)
        if bar.phase == "auction":
            row = np.array([0, 0, 0, 0, 0, 13], dtype=np.int64)
        else:
            row = self.kernel(
                self.match_state(item),
                self.compiled.market[index, column],
                self.costs,
                self.config,
                int(used[column]),
                bar.low,
                bar.high,
            )
        if row[5] == 8 and -item.values[LEFT] > self.account.quantities()[column]:
            row[5] = 9
        if row[5] == 7 and item.spend_left < self.available_cash(item):
            row[5] = 14
        self._apply(item, row)
        used[column] += abs(int(row[0]))
        if not item.values[LEFT]:
            self.finish(item.order_id, "filled")
        elif order.valid_for == "next_bar":
            self.finish(item.order_id, "expired")

    def _apply(self, item: PendingOrder, row: IntArray) -> None:
        quantity, price, commission, stamp, transfer, reason = map(int, row)
        order = self._orders[item.order_id - 1]
        cost = quantity * price + commission + stamp + transfer
        # A sale can raise cash toward unpaid tax even when it cannot clear all tax at once.
        # Existing buy reservations still cannot fund the sale's fees.
        if quantity < 0 and self.account.cash - cost < self.frozen_cash:
            row[:] = (0, 0, 0, 0, 0, 7)
            quantity, cost, commission, stamp, transfer, reason = 0, 0, 0, 0, 0, 7
        if quantity:
            self._fill(item, quantity, price, commission, stamp, transfer)
            self.account.cash -= cost
            if not 0 <= self.account.cash <= MAX_MONEY:
                raise OverflowError("cash exceeds supported bounds")
        state = "partially_filled" if order.filled + quantity else "accepted"
        order.session = self.data.sessions[self.data.day_index(self.index)]
        order.filled += quantity
        order.price_units = price if quantity else order.price_units
        order.notional_units = int(item.values[NOTIONAL])
        order.commission_units = int(item.values[PAID])
        order.stamp_duty_units += stamp
        order.transfer_fee_units += transfer
        order.reason = REASONS[reason]
        self._snapshot(item, state)

    def _fill(
        self,
        item: PendingOrder,
        quantity: int,
        price: int,
        commission: int,
        stamp: int,
        transfer: int,
    ) -> None:
        order = self._orders[item.order_id - 1]
        session = self.data.sessions[self.data.day_index(self.index)]
        point = self.data.timeline[self.index]
        self.fills.append(
            Fill(
                len(self.fills) + 1,
                order.order_id,
                order.intent_id,
                session,
                order.symbol,
                quantity,
                price,
                commission,
                stamp,
                transfer,
                point if isinstance(point, datetime) else None,
                reference_price_units=int(self.compiled.market[self.index, item.column, OPEN]),
            )
        )
        settlement = int(self.compiled.settlement[self.index, item.column])
        self.account.apply_fill(
            order.symbol, quantity, session, price, self.data.day_index(self.index), settlement
        )
        values = item.values
        values[LEFT] -= quantity
        values[NOTIONAL] += abs(quantity) * price
        values[PAID] += commission
        if quantity > 0:
            cost = quantity * price + commission + stamp + transfer
            self._reservations(item, max(0, int(values[BUDGET]) - cost), int(values[RESERVED]))
            item.spend_left -= cost
        else:
            self._reservations(item, int(values[BUDGET]), int(values[RESERVED]) + quantity)

    def end_day(self) -> None:
        day_index = self.data.day_index(self.index)
        for item in tuple(self.active.values()):
            if item.submitted < self.index and item.activation_day <= day_index:
                self.finish(item.order_id, "expired")

    def finish_all(self) -> None:
        for order_id in tuple(self.active):
            self.finish(order_id, "unexecuted")
