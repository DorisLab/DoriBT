"""Explicit adverse-price assumptions, separate from transaction fees."""

from dataclasses import dataclass, field

import numpy as np

from .execution import IntArray
from .validation import Number, integer, ratio


@dataclass(frozen=True)
class FixedTicks:
    ticks: int = 0

    def __post_init__(self) -> None:
        integer(self.ticks, 1, "ticks", 0, 1000)


@dataclass(frozen=True)
class FixedBps:
    bps: Number = 0

    def __post_init__(self) -> None:
        integer(self.bps, 100, "bps", 0, 1_000_000)


@dataclass(frozen=True)
class VolumeImpact:
    coefficient: Number = 0.1

    def __post_init__(self) -> None:
        ratio(self.coefficient, "impact coefficient")


@dataclass(frozen=True, kw_only=True)
class BarExecution:
    participation: Number = 0.05
    slippage: FixedTicks | FixedBps | VolumeImpact = field(default_factory=FixedTicks)

    def __post_init__(self) -> None:
        if not ratio(self.participation, "participation"):
            raise ValueError("participation must be positive")
        if not isinstance(self.slippage, (FixedTicks, FixedBps, VolumeImpact)):
            raise ValueError("unsupported slippage model")

    def compile(self) -> IntArray:
        if isinstance(self.slippage, FixedTicks):
            kind, size = 0, self.slippage.ticks
        elif isinstance(self.slippage, FixedBps):
            kind, size = 1, integer(self.slippage.bps, 100, "bps", 0, 1_000_000)
        else:
            kind, size = 2, ratio(self.slippage.coefficient, "impact coefficient")
        return np.array([ratio(self.participation), kind, size], dtype=np.int64)
