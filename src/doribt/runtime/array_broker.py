"""通用数组撮合器；Python 保留策略接口，数值内核推进全部活动委托。"""

import numpy as np

from doribt.accounting.orders import Fill, Order
from doribt.kernels.broker_loop import compiled_queue
from doribt.kernels.broker_state import (
    ACTIVATION,
    BUYING,
    CEILING,
    COLUMN,
    COMPLETE,
    INTENT,
    QUANTITY,
    REASON,
    REJECTED,
    SESSION,
    SPEND,
    STATE,
    STATES,
    SUBMITTED,
    UPDATED,
    VALID,
    WIDTH,
    order_snapshotter,
    restore_order,
)
from doribt.kernels.execution import IntArray
from doribt.runtime.broker import Broker, PendingOrder
from doribt.runtime.order_state import OrderState
from doribt.runtime.record_materialization import materialize_fills
from doribt.validation import Number


class ArrayBroker(Broker):
    def initialize_arrays(self, intrabar: IntArray) -> None:
        self._intrabar = intrabar
        self._order_snapshot = order_snapshotter(self.data)
        self._rows = np.zeros((64, WIDTH), dtype=np.int64)
        self._row_count = 0
        self._fill_rows = np.zeros((64, 7), dtype=np.int64)
        self._fill_count = 0
        self._queue_kernel = compiled_queue()
        self._money = np.zeros(2, dtype=np.int64)
        self._frozen = np.zeros(1, dtype=np.int64)
        self._share_array = np.zeros(len(self.data.symbols), dtype=np.int64)
        self._changed = np.zeros(len(self.data.symbols), dtype=np.int64)
        self._numeric_dirty: set[int] = set()

    def _grow_orders(self) -> None:
        if len(self._orders) <= len(self._rows):
            return
        rows = np.zeros((len(self._rows) * 2, WIDTH), dtype=np.int64)
        rows[: self._row_count] = self._rows[: self._row_count]
        self._rows = rows
        for identifier, item in self.active.items():
            if identifier <= self._row_count:
                item.values = rows[identifier - 1, :6]

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
        identifier = super().submit(
            symbol,
            quantity,
            valid_for,
            limit_price,
            max_spend,
            intent_id=intent_id,
            sizing_index=sizing_index,
        )
        self._grow_orders()
        row = self._rows[identifier - 1]
        order = self._orders[identifier - 1]
        column = self._columns[symbol]
        row[COLUMN], row[SUBMITTED], row[SESSION], row[UPDATED] = (
            column,
            self.index,
            self.index,
            self.index,
        )
        row[QUANTITY], row[INTENT], row[BUYING] = quantity, intent_id, quantity > 0
        row[VALID], row[CEILING] = (
            valid_for == "day",
            -1 if max_spend is None else order.max_spend_units,
        )
        if identifier in self.active:
            item = self.active[identifier]
            row[:6] = item.values
            item.values = row[:6]
            row[ACTIVATION], row[SPEND] = item.activation_day, item.spend_left
        else:
            row[STATE], row[REASON] = REJECTED, 6
            row[5] = order.limit_units
        self._row_count += 1
        return identifier

    def _snapshot(self, item: PendingOrder, state: str | None = None) -> None:
        if item.order_id > self._row_count:
            super()._snapshot(item, state)
            return
        row = self._rows[item.order_id - 1]
        row[UPDATED] = self.index
        if state is not None:
            row[STATE] = STATES.index(state)
        self._dirty_orders.add(item.order_id - 1)
        self._numeric_dirty.add(item.order_id - 1)

    def order_state(self, order_id: int) -> OrderState:
        index = order_id - 1
        if index in self._numeric_dirty:
            restore_order(self._rows[index], self._orders[index], self.data)
            self._numeric_dirty.remove(index)
        return self._orders[index]

    @property
    def orders(self) -> list[Order]:
        identifiers = sorted(self._dirty_orders)
        for index, row in zip(identifiers, self._rows[identifiers].tolist(), strict=True):
            snapshot = self._order_snapshot(row, index + 1)
            if index == len(self._snapshots):
                self._snapshots.append(snapshot)
            else:
                self._snapshots[index] = snapshot
        self._dirty_orders.clear()
        return self._snapshots

    @property
    def fill_count(self) -> int:
        return self._fill_count

    @property
    def fills(self) -> list[Fill]:
        if len(self._fills) < self._fill_count:
            self._fills.extend(
                materialize_fills(
                    self._fill_rows[len(self._fills) : self._fill_count],
                    self._rows,
                    self.data,
                    self.compiled.market,
                    start=len(self._fills),
                )
            )
        return self._fills

    def _reserve_batch(self, count: int) -> None:
        self.account.reserve_lots(count)
        needed = self._fill_count + count
        if needed > len(self._fill_rows):
            rows = np.zeros((max(needed, len(self._fill_rows) * 2), 7), dtype=np.int64)
            rows[: self._fill_count] = self._fill_rows[: self._fill_count]
            self._fill_rows = rows

    def advance(self, index: int) -> None:
        self.index = index
        if not self.active:
            return
        day = self.data.day_index(index)
        self.account.advance_day(day)
        self._reserve_batch(len(self.active))
        self._money[:] = self.account.cash, self.tax
        self._frozen[0] = self._frozen_cash
        self._share_array[:] = self._frozen_shares
        self._changed[:] = 0
        identifiers = np.fromiter(self.active, dtype=np.int64, count=len(self.active))
        self._fill_count = self._queue_kernel(
            identifiers,
            self._rows,
            index,
            day,
            self.data.sessions[day].toordinal(),
            self.compiled.market[index],
            self._intrabar[index],
            self.compiled.settlement[index],
            self.costs,
            self.config,
            self._money,
            self._frozen,
            self._share_array,
            self.account.numeric_state(),
            self._fill_rows,
            self._fill_count,
            self._changed,
        )
        self.account.cash = int(self._money[0])
        self._frozen_cash = int(self._frozen[0])
        self._frozen_shares[:] = self._share_array.tolist()
        self.account.changed_symbols.update(
            self.data.symbols[column] for column in np.flatnonzero(self._changed)
        )
        self._sync_active(identifiers, index)

    def _sync_active(self, identifiers: IntArray, index: int) -> None:
        for value in identifiers.tolist():
            row = self._rows[value - 1]
            if row[SUBMITTED] >= index:
                continue
            self._dirty_orders.add(value - 1)
            self._numeric_dirty.add(value - 1)
            if row[STATE] >= COMPLETE:
                del self.active[value]
            else:
                self.active[value].spend_left = int(row[SPEND])
