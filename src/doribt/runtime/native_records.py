"""可选原生列式审计物化；公开记录仍在返回前完整创建。"""

import hashlib
import importlib
import os
import sys
import sysconfig
from collections.abc import Callable, Sequence
from dataclasses import fields
from functools import cache
from pathlib import Path
from types import GetSetDescriptorType, ModuleType
from typing import cast

import numpy as np

from doribt.accounting.orders import REASONS, Fill, IntentRecord, Order
from doribt.accounting.records import _plain_record
from doribt.accounting.taxes import TaxLotRecord
from doribt.kernels import broker_state as state
from doribt.kernels.execution import OPEN, IntArray
from doribt.market.data import MarketData

KINDS = (Order, Fill, IntentRecord, TaxLotRecord)
NAMES: dict[type[object], tuple[str, ...]] = {
    kind: tuple(field.name for field in fields(kind)) for kind in KINDS
}
type Column = list[object]
type ObjectArray = np.ndarray[tuple[int, ...], np.dtype[np.object_]]
type ColumnSource = Sequence[object] | ObjectArray
type Records = tuple[
    tuple[Order, ...], tuple[IntentRecord, ...], tuple[Fill, ...], tuple[TaxLotRecord, ...]
]


def _compatible_runtime() -> bool:
    # 不先导入扩展再检查 free-threaded，避免导入本身改变解释器 GIL 行为。
    return (
        sys.implementation.name == "cpython"
        and sys.version_info[:2] == (3, 13)
        and sys.platform == "linux"
        and sysconfig.get_platform() == "linux-x86_64"
        and not sysconfig.get_config_var("Py_GIL_DISABLED")
        and not sysconfig.get_config_var("Py_DEBUG")
    )


@cache
def _extension() -> ModuleType | None:
    if not _compatible_runtime():
        return None
    try:
        return importlib.import_module("doribt._native_records")
    except ImportError:
        return None


def _supported(kind: type[object]) -> bool:
    return (
        _plain_record(kind)
        and kind.__getattribute__ is object.__getattribute__
        and isinstance(kind.__dict__.get("__dict__"), GetSetDescriptorType)
    )


def available() -> bool:
    mode = os.environ.get("DORIBT_NATIVE_RECORDS", "auto")
    if mode not in ("auto", "required", "off"):
        raise ValueError("DORIBT_NATIVE_RECORDS 必须是 auto、required 或 off")
    if mode == "off":
        return False
    module = _extension()
    supported = (
        module is not None
        and getattr(module, "API_VERSION", None) == 1
        and all(_supported(kind) for kind in KINDS)
    )
    if not supported and mode == "required":
        raise RuntimeError("当前构建无法使用原生审计物化器；请安装经过验证的原生 wheel")
    return supported


def implementation_identity() -> str:
    if not available():
        return "python-eager-records-v1"
    module = _extension()
    assert module is not None and module.__file__ is not None
    return (
        "native-column-records-v1:" + hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    )


def _create[T](kind: type[T], columns: list[Column]) -> tuple[T, ...]:
    module = _extension()
    if module is None:
        raise RuntimeError("原生审计模块不可用")
    constructor = cast(
        Callable[[type[T], tuple[str, ...], tuple[Column, ...]], tuple[T, ...]],
        module.bulk_columns,
    )
    return constructor(kind, NAMES[kind], tuple(columns))


def _values(values: IntArray) -> Column:
    return cast(Column, values.tolist())


def _take(values: ColumnSource, indices: IntArray) -> Column:
    if not len(indices):
        return []
    if not isinstance(values, np.ndarray) and len(indices) < len(values):
        return [values[index] for index in indices.tolist()]
    return cast(Column, np.asarray(values, dtype=object)[indices].tolist())


class _RecordLookups:
    """稀疏记录直接取值，密集记录共享本次物化的时间轴数组。"""

    def __init__(self, data: MarketData) -> None:
        self.data = data
        self._timeline: ColumnSource = data.timeline
        self._sessions: ObjectArray | None = None

    def timeline(self, indices: IntArray) -> Column:
        if len(indices) >= len(self._timeline) and not isinstance(self._timeline, np.ndarray):
            self._timeline = np.asarray(self._timeline, dtype=object)
        return _take(self._timeline, indices)

    def sessions(self, indices: IntArray) -> Column:
        if self._sessions is not None:
            return _take(self._sessions, indices)
        if len(indices) < len(self.data.timeline):
            return [self.data.sessions[self.data.day_index(index)] for index in indices.tolist()]
        days = (
            np.asarray(self.data.clock.day_indices, dtype=np.int64)
            if self.data.clock
            else np.arange(len(self.data.sessions))
        )
        self._sessions = np.asarray(self.data.sessions, dtype=object)[days]
        return _take(self._sessions, indices)


def _nullable(values: IntArray, mask: np.ndarray[tuple[int, ...], np.dtype[np.bool_]]) -> Column:
    result = values.astype(object)
    result[mask] = None
    return cast(Column, result.tolist())


def _repeat(value: object, count: int) -> Column:
    return [value] * count


def _orders(rows: IntArray, lookup: _RecordLookups) -> tuple[Order, ...]:
    if not len(rows):
        return ()

    def at(column: int) -> Column:
        return _values(rows[:, column])

    return _create(
        Order,
        [
            list(range(1, len(rows) + 1)),
            at(state.INTENT),
            lookup.sessions(rows[:, state.SESSION]),
            _take(lookup.data.symbols, rows[:, state.COLUMN]),
            at(state.QUANTITY),
            at(state.FILLED),
            at(state.PRICE),
            at(2),
            at(state.STAMP_PAID),
            at(state.TRANSFER_PAID),
            _take(REASONS, rows[:, state.REASON]),
            lookup.timeline(rows[:, state.SUBMITTED]),
            lookup.timeline(rows[:, state.UPDATED]),
            _take(state.STATES, rows[:, state.STATE]),
            at(1),
            _take(("next_bar", "day"), rows[:, state.VALID]),
            at(5),
            at(3),
            at(4),
            _nullable(rows[:, state.CEILING], rows[:, state.CEILING] < 0),
        ],
    )


def _intents(rows: IntArray, lookup: _RecordLookups) -> tuple[IntentRecord, ...]:
    if not len(rows):
        return ()
    column, created, quantity, closed, status, reason, weight, mode, sized = rows.T
    sized_times = lookup.timeline(sized)
    for index in np.flatnonzero(sized < 0).tolist():
        sized_times[index] = None
    return _create(
        IntentRecord,
        [
            list(range(1, len(rows) + 1)),
            lookup.sessions(created),
            _take(lookup.data.symbols, column),
            _repeat("target", len(rows)),
            _nullable(quantity, (mode == 2) & (sized < 0)),
            _take(("active", "fulfilled", "cancelled", "unexecuted"), status),
            lookup.sessions(closed),
            _take(("", "target_below_minimum", "target_replaced", "end_of_data"), reason),
            _repeat((), len(rows)),
            _nullable(weight, weight < 0),
            _take(("quantity", "close", "execution"), mode),
            sized_times,
        ],
    )


def _fills(
    rows: IntArray,
    order_rows: IntArray,
    lookup: _RecordLookups,
    market: IntArray,
) -> tuple[Fill, ...]:
    if not len(rows):
        return ()
    order_ids, indices, quantity, price, commission, stamp, transfer = rows.T
    columns = order_rows[order_ids - 1, state.COLUMN]
    return _create(
        Fill,
        [
            list(range(1, len(rows) + 1)),
            _values(order_ids),
            _values(order_rows[order_ids - 1, state.INTENT]),
            lookup.sessions(indices),
            _take(lookup.data.symbols, columns),
            _values(quantity),
            _values(price),
            _values(commission),
            _values(stamp),
            _values(transfer),
            lookup.timeline(indices) if lookup.data.clock else _repeat(None, len(rows)),
            _values(market[indices, columns, OPEN]),
        ],
    )


def _tax_lots(rows: IntArray, data: MarketData) -> tuple[TaxLotRecord, ...]:
    selected = np.flatnonzero(rows[:, 2])
    if not len(selected):
        return ()
    return _create(
        TaxLotRecord,
        [
            _values(selected + 1),
            _take(data.symbols, rows[selected, 0]),
            _take(data.sessions, rows[selected, 1]),
            _values(rows[selected, 2]),
            _repeat((), len(selected)),
        ],
    )


def materialize(
    rows: IntArray,
    intentions: IntArray,
    lots: IntArray,
    fill_rows: IntArray,
    data: MarketData,
    market: IntArray,
) -> Records:
    # 不捕获原生构造异常后暗中回退；required 路径必须可独立验证。
    if not available():
        raise RuntimeError("原生审计物化器未启用")
    lookup = _RecordLookups(data)
    return (
        _orders(rows, lookup),
        _intents(intentions, lookup),
        _fills(fill_rows, rows, lookup, market),
        _tax_lots(lots, data),
    )
