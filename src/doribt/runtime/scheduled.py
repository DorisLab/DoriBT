"""Precomputed targets skip stable intervals, retaining the formal broker and rights books."""

from collections.abc import Callable, Mapping
from typing import cast

import numpy as np

from doribt.accounting.costs import Costs
from doribt.kernels.compiled import PreparedData
from doribt.kernels.execution import STATUS
from doribt.kernels.segments import scanner, value_span
from doribt.provenance import RunInfo
from doribt.reporting.result import BacktestResult
from doribt.runtime.bar_runtime import BarRun
from doribt.runtime.context import Context
from doribt.runtime.slippage import BarExecution
from doribt.runtime.targets import PositionTargets, WeightTargets


class ScheduledRun(BarRun):
    def __init__(
        self,
        prepared: PreparedData,
        initial_cash: int,
        costs: Costs,
        backend: str,
        execution: BarExecution,
        targets: PositionTargets | WeightTargets,
    ) -> None:
        super().__init__(prepared, initial_cash, costs, backend, execution)
        self.precomputed_targets = targets
        self.scan = scanner(backend)
        self.intrabar = prepared.intrabar
        from doribt.runtime.compiled_schedule import eligible as eligible_schedule
        from doribt.runtime.compiled_targets import eligible

        if eligible(self) or eligible_schedule(self):
            return
        self.decisions = np.zeros(len(self.data.timeline), dtype=np.bool_)
        self.decisions[0] = True
        values = targets.quantities if isinstance(targets, PositionTargets) else targets.weights
        for series in values.values():
            array = np.asarray(series)
            self.decisions[1:] |= array[1:] != array[:-1]
        if isinstance(targets, WeightTargets) and targets.rebalance:
            self.decisions[:] = True
        boundaries = self.decisions.copy()
        days = (
            np.asarray(self.data.clock.day_indices)
            if self.data.clock
            else np.arange(len(boundaries))
        )
        boundaries[1:] |= days[1:] != days[:-1]
        boundaries[:-1] |= days[1:] != days[:-1]
        # Inactive rows have no compiled rule. Submission uses the preceding row,
        # so inspect both the transition bar and its successor without skipping.
        statuses = self.compiled.market[:, :, STATUS]
        transitions = np.any(statuses[1:] != statuses[:-1], axis=1)
        boundaries[1:] |= transitions
        boundaries[2:] |= transitions[:-1]
        boundaries[-1] = True
        self.boundaries = np.flatnonzero(boundaries)

    def execute(self, strategy: Callable[[Context], None], info: RunInfo) -> BacktestResult:
        from doribt.runtime.compiled_schedule import eligible as eligible_schedule
        from doribt.runtime.compiled_schedule import execute as execute_schedule
        from doribt.runtime.compiled_targets import eligible, execute

        if eligible_schedule(self):
            return execute_schedule(self, info)
        if eligible(self):
            return execute(self, info)
        return super().execute(strategy, info)

    def _drive(self, strategy: Callable[[Context], None]) -> None:
        index, count = 0, len(self.data.timeline)
        while index < count:
            previous_fills = self.broker.fill_count
            self._open(index)
            self._close(index)
            if self.decisions[index]:
                self._invoke_targets(strategy, index)
            changed = self.decisions[index] or previous_fills != self.broker.fill_count
            index = index + 1 if changed else self._skip(index)

    def _invoke_targets(self, strategy: Callable[[Context], None], index: int) -> None:
        targets = self.precomputed_targets
        if type(targets) is not PositionTargets:
            self._invoke(strategy, index)
            return
        try:
            self._place_positions(targets, index)
        except Exception as error:
            session = self.data.timeline[index]
            raise RuntimeError(f"strategy failed at close on {session}: {error}") from error

    def _place_positions(self, targets: PositionTargets, index: int) -> None:
        # 精确内置类型已在构造和 run 入口验证；只提交发生变化的目标。
        session = self.data.sessions[self.data.day_index(index)]
        quantities = cast(Mapping[str, tuple[int, ...]], targets.quantities)
        for symbol, series in quantities.items():
            if index == 0 or series[index] != series[index - 1]:
                self.book.place(session, symbol, "target", int(series[index]))

    def _can_scan(self, index: int) -> bool:
        """Do not skip a bar that must fulfill an intent or issue a child order."""
        quantities = self.holdings[index] + self.pending_shares[index]
        for symbol, intent in self.book.pending.items():
            column = self.data.symbols.index(symbol)
            if quantities[column] == intent.quantity:
                return False
            child = self.targets.children.get(intent.intent_id)
            if child in self.broker.active:
                continue
            if intent.reason == "target_below_minimum":
                continue  # Rules cannot change inside a trading date.
            if child is None:
                return False
            order = self.broker.order_state(child)
            if (
                order.status == "filled"
                or order.session != self.data.sessions[self.data.day_index(index)]
            ):
                return False
        return True

    def _skip(self, index: int) -> int:
        start = index + 1
        if start == len(self.data.timeline) or not self._can_scan(index):
            return start
        stop = int(self.boundaries[np.searchsorted(self.boundaries, start)])
        if stop <= start:
            return start
        active = tuple(self.broker.active.values())
        columns = np.array([item.column for item in active], dtype=np.int64)
        states = np.array(
            [self.broker.match_state(item) for item in active], dtype=np.int64
        ).reshape(-1, 6)
        end = self.scan(
            start,
            stop,
            columns,
            states,
            self.compiled.market,
            self.intrabar,
            self.costs,
            self.broker.config,
        )
        if end > start:
            # Preserve the final no-fill reason, timestamp and reservations exactly.
            self._open(end - 1)
            self._close(end - 1)
            self._copy_span(start, end)
        return end

    def _copy_span(self, start: int, end: int) -> None:
        for array in (
            self.cash,
            self.holdings,
            self.sellable,
            self.pending_shares,
            self.receivable,
            self.tax_payable,
            self.reserved_cash,
            self.reserved_shares,
        ):
            array[start:end] = array[end - 1]
        self.equity[start:end] = value_span(
            self.compiled.closes[start:end],
            self.holdings[end - 1] + self.pending_shares[end - 1],
            int(self.cash[end - 1] + self.receivable[end - 1] - self.tax_payable[end - 1]),
        )
