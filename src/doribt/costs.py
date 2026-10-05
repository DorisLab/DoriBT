"""Account-specific execution assumptions, separate from historical market rules."""

from dataclasses import dataclass

import numpy as np

from .execution import IntArray
from .validation import Number, amount, integer, ratio


@dataclass(frozen=True, kw_only=True)
class Costs:
    commission: Number = "0.0003"
    minimum_commission: Number = "5.00"
    slippage_ticks: int = 0

    def __post_init__(self) -> None:
        ratio(self.commission, "commission")
        minimum = amount(self.minimum_commission, "minimum_commission")
        if minimum % 100:
            raise ValueError("minimum commission must use whole cents")
        integer(self.slippage_ticks, 1, "slippage_ticks", 0, 1000)

    def compile(self) -> IntArray:
        return np.array(
            [
                ratio(self.commission),
                amount(self.minimum_commission),
                self.slippage_ticks,
            ],
            dtype=np.int64,
        )
