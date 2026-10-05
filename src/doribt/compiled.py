"""Validated data compiled once to numeric daily inputs."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import numpy as np
from numpy.typing import NDArray

from .data import MarketData
from .execution import IntArray
from .instruments import TradingStatus
from .validation import ratio


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


def prepare(data: MarketData) -> PreparedData:
    return PreparedData(
        data,
        compile_data(data),
        MappingProxyType({field: data.prices(field) for field in ("open", "high", "low", "close")}),
    )


def _freeze(values: IntArray) -> IntArray:
    # Bytes-backed arrays cannot be made writable through result.close_units either.
    return np.frombuffer(values.tobytes(), dtype=np.int64).reshape(values.shape)


def compile_data(data: MarketData) -> CompiledData:
    shape = (len(data.sessions), len(data.symbols))
    market = np.zeros((*shape, 14), dtype=np.int64)
    closes = np.zeros(shape, dtype=np.int64)
    settlement = np.zeros(shape, dtype=np.int64)
    for offset, bar in enumerate(data.bars):
        row, column = divmod(offset, len(data.symbols))
        market[row, column, :4] = (
            bar.open,
            int(bar.status),
            bar.upper_limit or 0,
            bar.lower_limit or 0,
        )
        closes[row, column] = bar.close
        if bar.status not in (TradingStatus.TRADING, TradingStatus.SUSPENDED):
            continue
        rule = data.rules.at(bar.symbol, bar.session).rule
        market[row, column, 4:] = (
            rule.tick_units,
            rule.buy_minimum,
            rule.buy_step,
            rule.sell_step,
            ratio(rule.stamp_duty_sell),
            ratio(rule.transfer_fee),
            bar.volume,
            int(rule.allow_odd_lot_liquidation),
            rule.sell_minimum,
            rule.order_maximum,
        )
        settlement[row, column] = rule.settlement_days
    return CompiledData(_freeze(market), _freeze(closes), _freeze(settlement))
