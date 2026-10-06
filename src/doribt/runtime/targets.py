"""Date-identified precomputed weights, routed through the close callback contract."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property
from types import MappingProxyType
from typing import cast

import numpy as np
from numpy.typing import ArrayLike

from doribt.market.clock import time_points
from doribt.market.data import MarketData
from doribt.runtime.context import Context
from doribt.validation import DateLike, integer, ratio


@dataclass(frozen=True, kw_only=True)
class PositionTargets:
    """Fixed shares at each close; only changes replace a security's active target.

    Omitted securities are unchanged. Equal consecutive values retain the existing
    intention, including corporate-action adjustments to that intention.
    """

    sessions: Sequence[DateLike]
    quantities: Mapping[str, ArrayLike]

    def __post_init__(self) -> None:
        dates = time_points(self.sessions)
        object.__setattr__(self, "sessions", dates)
        normalized: dict[str, tuple[int, ...]] = {}
        for symbol, values in self.quantities.items():
            array = np.asarray(values)
            if array.shape != (len(dates),):
                raise ValueError(f"quantity length must match sessions: {symbol}")
            normalized[symbol] = tuple(
                integer(value, 1, "target quantity", 0, 1_000_000_000) for value in array.tolist()
            )
        object.__setattr__(self, "quantities", MappingProxyType(normalized))

    def validate(self, data: MarketData) -> None:
        if tuple(self.sessions) != data.timeline:
            raise ValueError("target sessions must exactly match market sessions")
        if set(self.quantities) - set(data.symbols):
            raise ValueError("targets contain unknown securities")

    @cached_property
    def _provenance_json(self) -> str:
        from doribt.provenance import _strategy_info, encode

        return encode(_strategy_info(self))

    def __call__(self, context: Context) -> None:
        index = context.bar_index
        quantities = cast(Mapping[str, tuple[int, ...]], self.quantities)
        changes = {
            symbol: values[index]
            for symbol, values in quantities.items()
            if index == 0 or values[index] != values[index - 1]
        }
        context.target_positions(changes)


@dataclass(frozen=True, kw_only=True)
class WeightTargets:
    sessions: Sequence[DateLike]
    weights: Mapping[str, ArrayLike]
    rebalance: bool = False

    def __post_init__(self) -> None:
        dates = time_points(self.sessions)
        object.__setattr__(self, "sessions", dates)
        normalized: dict[str, tuple[float, ...]] = {}
        totals = np.zeros(len(dates), dtype=np.int64)
        for symbol, values in self.weights.items():
            array = np.asarray(values)
            if array.shape != (len(dates),):
                raise ValueError(f"weight length must match sessions: {symbol}")
            scaled = tuple(ratio(value, "weight") for value in array.tolist())
            totals += np.array(scaled, dtype=np.int64)
            normalized[symbol] = tuple(value / 1_000_000 for value in scaled)
        if np.any(totals > 1_000_000):
            raise ValueError("long-only target weights must sum to at most one")
        if not isinstance(self.rebalance, bool):
            raise ValueError("rebalance must be boolean")
        object.__setattr__(self, "weights", MappingProxyType(normalized))

    def validate(self, data: MarketData) -> None:
        if tuple(self.sessions) != data.timeline:
            raise ValueError("target sessions must exactly match market sessions")
        if set(self.weights) - set(data.symbols):
            raise ValueError("targets contain unknown securities")

    @cached_property
    def _provenance_json(self) -> str:
        from doribt.provenance import _strategy_info, encode

        return encode(_strategy_info(self))

    def __call__(self, context: Context) -> None:
        index = context._index
        weights = {
            symbol: cast(tuple[float, ...], values)[index]
            for symbol, values in self.weights.items()
        }
        context.target_weights(weights, rebalance=self.rebalance)
