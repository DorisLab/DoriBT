"""An explicitly dated comparison curve; no implicit price download or alignment."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from doribt.market.clock import time_points
from doribt.validation import DateLike


@dataclass(frozen=True, kw_only=True)
class Benchmark:
    """Positive price/index levels, rebased at the first supplied close.

    Supply total-return levels if distributions should be included. DoriBT does
    not infer whether an external index is a price or total-return index.
    """

    sessions: Sequence[DateLike]
    prices: ArrayLike
    name: str
    source: str

    def __post_init__(self) -> None:
        sessions = time_points(self.sessions)
        prices = np.asarray(self.prices, dtype=np.float64)
        if prices.shape != (len(sessions),):
            raise ValueError("benchmark prices must match sessions")
        if not np.all(np.isfinite(prices)) or np.any(prices <= 0):
            raise ValueError("benchmark prices must be finite and positive")
        if not self.name.strip() or not self.source.strip():
            raise ValueError("benchmark name and source are required")
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            ratios = prices / prices[0]
            changes = prices[1:] / prices[:-1]
        if (
            not np.all(np.isfinite(ratios))
            or not np.all(np.isfinite(changes))
            or np.any(ratios <= 0)
            or np.any(changes <= 0)
        ):
            raise ValueError("benchmark price ratios exceed floating-point bounds")
        object.__setattr__(self, "sessions", sessions)
        object.__setattr__(self, "prices", tuple(float(value) for value in prices))

    @property
    def nav(self) -> NDArray[np.float64]:
        values: NDArray[np.float64] = np.asarray(self.prices, dtype=np.float64)
        return values / float(values[0])

    def validate(self, sessions: Sequence[DateLike]) -> None:
        if tuple(sessions) != self.sessions:
            raise ValueError("benchmark sessions must exactly match result sessions")
