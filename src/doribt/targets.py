"""Date-identified precomputed weights, routed through the close callback contract."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

import numpy as np
from numpy.typing import ArrayLike

from .bars import calendar_days
from .context import Context
from .data import MarketData
from .validation import DateLike, ratio


@dataclass(frozen=True, kw_only=True)
class WeightTargets:
    sessions: Sequence[DateLike]
    weights: Mapping[str, ArrayLike]
    rebalance: bool = False

    def __post_init__(self) -> None:
        dates = calendar_days(list(self.sessions))
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
        if tuple(self.sessions) != data.sessions:
            raise ValueError("target sessions must exactly match market sessions")
        if set(self.weights) - set(data.symbols):
            raise ValueError("targets contain unknown securities")

    def __call__(self, context: Context) -> None:
        index = context._index
        weights = {
            symbol: cast(tuple[float, ...], values)[index]
            for symbol, values in self.weights.items()
        }
        context.target_weights(weights, rebalance=self.rebalance)
