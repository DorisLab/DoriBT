"""Validated data compiled once to numeric daily inputs."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from functools import cached_property
from types import MappingProxyType

import numpy as np
from numpy.typing import NDArray

from doribt.kernels.execution import IntArray
from doribt.market.bars import Bar
from doribt.market.data import MarketData
from doribt.market.instruments import TradingStatus
from doribt.market.rules import TradingRule
from doribt.validation import ratio

FIELDS = ("open", "high", "low", "close")


class _History(Mapping[str, NDArray[np.float64]]):
    """OHLC 字段按需准备，缓存只读原始价格，不缓存账户或复权时点。"""

    def __init__(self, data: MarketData) -> None:
        self._data = data
        self._cache: dict[str, NDArray[np.float64]] = {}

    def __len__(self) -> int:
        return len(FIELDS)

    def __iter__(self) -> Iterator[str]:
        return iter(FIELDS)

    def __contains__(self, field: object) -> bool:
        return field in FIELDS

    def __getitem__(self, field: str) -> NDArray[np.float64]:
        if field not in FIELDS:
            raise KeyError(field)
        if field not in self._cache:
            values = self._data.prices(field)
            self._cache[field] = np.frombuffer(values.tobytes(), dtype=np.float64).reshape(
                values.shape
            )
        return self._cache[field]


@dataclass(frozen=True)
class CompiledData:
    market: IntArray
    closes: IntArray
    settlement: IntArray


@dataclass(frozen=True)
class PreparedData:
    """Immutable market preparation reusable across independent accounts."""

    data: MarketData
    compiled: CompiledData
    history: Mapping[str, NDArray[np.float64]]

    @cached_property
    def columns(self) -> Mapping[str, int]:
        """证券列索引与公开 symbols 元组同序，跨回调复用。"""
        return MappingProxyType({symbol: column for column, symbol in enumerate(self.data.symbols)})

    @cached_property
    def provenance_json(self) -> str:
        from doribt.provenance import data_info, encode

        return encode(data_info(self.data))

    @cached_property
    def intrabar(self) -> IntArray:
        """Low/high/auction flags, needed only by scheduled bar execution."""
        shape = (*self.compiled.closes.shape, 3)
        return _freeze(
            np.array(
                [(bar.low, bar.high, int(bar.phase == "auction")) for bar in self.data.bars],
                dtype=np.int64,
            ).reshape(shape)
        )


def prepare(data: MarketData) -> PreparedData:
    return PreparedData(data, compile_data(data), _History(data))


def _freeze(values: IntArray) -> IntArray:
    # bytes 支撑的数组不能经由结果 close_units 重新启用写入。
    return np.frombuffer(values.tobytes(), dtype=np.int64).reshape(values.shape)


def _compile_rule(rule: TradingRule) -> tuple[int, ...]:
    return (
        rule.tick_units,
        rule.buy_minimum,
        rule.buy_step,
        rule.sell_step,
        ratio(rule.stamp_duty_sell),
        ratio(rule.transfer_fee),
        0,
        int(rule.allow_odd_lot_liquidation),
        rule.sell_minimum,
        rule.order_maximum,
        rule.settlement_days,
    )


class _RuleRows:
    """每证券交易日查询一次规则，相同规范规则复用数值转换。"""

    def __init__(self, data: MarketData) -> None:
        self._data = data
        self._dates: list[date | None] = [None] * len(data.symbols)
        self._rows: list[tuple[int, ...]] = [()] * len(data.symbols)
        self._cache: dict[TradingRule, tuple[int, ...]] = {}

    def at(self, bar: Bar, column: int) -> tuple[int, ...]:
        if self._dates[column] != bar.session:
            rule = self._data.rules.at(bar.symbol, bar.session).rule
            if rule not in self._cache:
                self._cache[rule] = _compile_rule(rule)
            self._rows[column] = self._cache[rule]
            self._dates[column] = bar.session
        return self._rows[column]


def compile_data(data: MarketData) -> CompiledData:
    shape = (len(data.timeline), len(data.symbols))
    market = np.zeros((*shape, 14), dtype=np.int64)
    closes = np.zeros(shape, dtype=np.int64)
    settlement = np.zeros(shape, dtype=np.int64)
    rules = _RuleRows(data)
    for offset, bar in enumerate(data.bars):
        row, column = divmod(offset, shape[1])
        market[row, column, :4] = (
            bar.open,
            int(bar.status),
            bar.upper_limit or 0,
            bar.lower_limit or 0,
        )
        closes[row, column] = bar.close
        if bar.status not in (TradingStatus.TRADING, TradingStatus.SUSPENDED):
            continue
        values = rules.at(bar, column)
        market[row, column, 4:] = values[:-1]
        market[row, column, 10] = bar.volume
        settlement[row, column] = values[-1]
    return CompiledData(_freeze(market), _freeze(closes), _freeze(settlement))
