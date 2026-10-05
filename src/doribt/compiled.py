"""Validated data compiled once to numeric daily inputs."""

from dataclasses import dataclass

import numpy as np

from .data import MarketData
from .execution import IntArray
from .instruments import TradingStatus
from .validation import ratio


@dataclass(frozen=True)
class CompiledData:
    market: IntArray
    closes: IntArray
    settlement: IntArray


def compile_data(data: MarketData) -> CompiledData:
    shape = (len(data.sessions), len(data.symbols))
    market = np.zeros((*shape, 12), dtype=np.int64)
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
        )
        settlement[row, column] = rule.settlement_days
    return CompiledData(market, closes, settlement)
