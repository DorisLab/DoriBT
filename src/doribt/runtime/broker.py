"""Order lifetime, reservations and immutable fill records around the numeric matcher."""

from dataclasses import dataclass, replace
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
    charges,
)
from doribt.market.data import MarketData
from doribt.runtime.matching import (
    BUDGET,
    LEFT,
    LIMIT,
    NOTIONAL,
    PAID,
    RESERVED,
    Matcher,
    slip_price,
)
from doribt.validation import MAX_MONEY, Number, amount


@dataclass
class PendingOrder:
    order_id: int
    column: int
    submitted: int
    activation_day: int
    values: IntArray
    spend_left: int = MAX_MONEY


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
    ) -> None:
        self.data, self.compiled, self.account = data, compiled, account
        self.costs, self.config, self.kernel = costs, config, kernel
        self.orders: list[Order] = []
        self.fills: list[Fill] = []
        self.active: dict[int, PendingOrder] = {}
        self.index = 0
        self.tax = 0

    @property
    def frozen_cash(self) -> int:
        return sum(int(item.values[BUDGET]) for item in self.active.values())

    def frozen_shares(self, column: int) -> int:
        return sum(
            int(item.values[RESERVED]) for item in self.active.values() if item.column == column
        )

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
        column, index = self.data.symbols.index(symbol), self.index
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
        order_id = len(self.orders) + 1
        now, session = self.data.timeline[index], self.data.sessions[self.data.day_index(index)]
        self.orders.append(
            Order(
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
            )
            self.active[order_id] = item
            self._reserve(item, sizing_index)
        return order_id

    def _reserve(self, item: PendingOrder, sizing_index: int | None = None) -> None:
        values, index, column = item.values, self.index, item.column
        if values[LEFT] < 0:
            available = int(self.account.quantities(self.data.day_index(index))[column])
            values[RESERVED] = min(
                -int(values[LEFT]), max(0, available - self.frozen_shares(column))
            )
        else:
            rule = self.compiled.market[
                index if sizing_index is None else sizing_index, column
            ].copy()
            price = int(rule[OPEN])
            if sizing_index is None:
                rule[OPEN] = self.compiled.closes[index, column]
                price = int(values[LIMIT]) or slip_price(
                    rule, self.config, int(values[LEFT]), 0, True
                )
            if price <= 0 or values[LEFT] > MAX_MONEY // price:
                raise OverflowError("order reservation exceeds supported bounds")
            notional = int(values[LEFT]) * price
            fees = charges(notional, int(self.costs[0]), int(self.costs[1]), 0, int(rule[9]))
            available = max(0, self.account.cash - self.tax - self.frozen_cash)
            values[BUDGET] = min(available, notional + sum(fees), item.spend_left)
        self._snapshot(item)

    def match_state(self, item: PendingOrder) -> IntArray:
        """预留估值保护其他挂单；可支出金额还包括当前未占用现金。"""
        state = item.values.copy()
        if state[LEFT] > 0:
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
        item.values[BUDGET] = item.values[RESERVED] = 0
        self._snapshot(item, state)

    def _snapshot(self, item: PendingOrder, state: str | None = None) -> None:
        order = self.orders[item.order_id - 1]
        self.orders[item.order_id - 1] = replace(
            order,
            updated_at=self.data.timeline[self.index],
            state=state or order.state,
            frozen_cash_units=int(item.values[BUDGET]),
            frozen_quantity=int(item.values[RESERVED]),
        )

    def advance(self, index: int) -> None:
        self.index = index
        used = np.zeros(len(self.data.symbols), dtype=np.int64)
        queue = sorted(
            self.active.values(), key=lambda item: (item.values[LEFT] > 0, item.order_id)
        )
        for item in queue:
            if item.submitted < index:
                self._attempt(item, used)

    def _attempt(self, item: PendingOrder, used: IntArray) -> None:
        index, column = self.index, item.column
        order = self.orders[item.order_id - 1]
        bar = self.data.bars[index * len(self.data.symbols) + column]
        if item.values[LEFT] < 0:
            # Newly settled shares may fund an order submitted at yesterday's final close.
            item.values[RESERVED] = 0
            self._reserve(item)
        row = np.zeros(6, dtype=np.int64)
        if bar.phase == "auction":
            row[5] = 13
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
        order = self.orders[item.order_id - 1]
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
        self.orders[item.order_id - 1] = replace(
            order,
            session=self.data.sessions[self.data.day_index(self.index)],
            filled=order.filled + quantity,
            price_units=price if quantity else order.price_units,
            notional_units=int(item.values[NOTIONAL]),
            commission_units=int(item.values[PAID]),
            stamp_duty_units=order.stamp_duty_units + stamp,
            transfer_fee_units=order.transfer_fee_units + transfer,
            reason=REASONS[reason],
            state=state,
        )
        self._snapshot(item)

    def _fill(
        self,
        item: PendingOrder,
        quantity: int,
        price: int,
        commission: int,
        stamp: int,
        transfer: int,
    ) -> None:
        order = self.orders[item.order_id - 1]
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
        event = replace(order, session=session, filled=quantity, price_units=price)
        settlement = int(self.compiled.settlement[self.index, item.column])
        self.account.apply(event, self.data.day_index(self.index), settlement)
        values = item.values
        values[LEFT] -= quantity
        values[NOTIONAL] += abs(quantity) * price
        values[PAID] += commission
        if quantity > 0:
            cost = quantity * price + commission + stamp + transfer
            values[BUDGET] = max(0, int(values[BUDGET]) - cost)
            item.spend_left -= cost
        else:
            values[RESERVED] += quantity

    def end_day(self) -> None:
        day_index = self.data.day_index(self.index)
        for item in tuple(self.active.values()):
            if item.submitted < self.index and item.activation_day <= day_index:
                self.finish(item.order_id, "expired")

    def finish_all(self) -> None:
        for order_id in tuple(self.active):
            self.finish(order_id, "unexecuted")
