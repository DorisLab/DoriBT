"""Dated close decisions and a single-account research interface.

This is an ergonomic entry to the existing budget model, not the future
multi-asset order engine. The legacy array API remains available for batches.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from .api import backtest
from .models import Config, DailyBars, session_dates
from .typing import DateArray, FlagArray, FloatArray, IntArray, RecordArray


@dataclass(frozen=True, kw_only=True)
class Costs:
    commission_rate: float = 0.0003
    minimum_commission: float = 5.0
    slippage_ticks: int = 1


@dataclass(frozen=True, kw_only=True)
class CloseSignals:
    """Desired long/flat state known at each session's close, not order events.

    True means hold; False means flat. The next input session is the earliest
    execution opportunity. A continuous True does not rebalance a held position.
    """

    sessions: ArrayLike
    hold: ArrayLike

    def execution_regime(self, sessions: DateArray) -> FlagArray:
        dates = session_dates(self.sessions)
        if not np.array_equal(dates, sessions):
            raise ValueError(
                "signal sessions must match data sessions exactly; no implicit alignment"
            )
        hold = np.asarray(self.hold)
        if hold.shape != dates.shape or hold.dtype.kind != "b":
            raise ValueError("hold must be one boolean close decision per session")
        regime = np.zeros(len(dates), dtype=np.int8)
        regime[1:] = hold[:-1]
        return regime


@dataclass(frozen=True)
class BacktestResult:
    """Single-account arrays, dated fills and the configuration that produced them."""

    sessions: DateArray
    equity: FloatArray
    cash: FloatArray
    position: IntArray
    fills: RecordArray
    blocked: FlagArray
    config: Config
    backend: str
    model: str

    @property
    def total_return(self) -> float:
        return float(self.equity[-1] / self.config.initial_cash - 1)

    @property
    def max_drawdown(self) -> float:
        """Positive loss fraction, including initial capital in the high-water mark."""
        curve = np.r_[self.config.initial_cash, self.equity]
        peaks = np.maximum.accumulate(curve)
        return float(np.max(1 - curve / peaks))

    def stats(self) -> dict[str, float | int]:
        """Basic metrics with no implicit annualization or risk-free-rate assumptions."""
        return {
            "initial_cash": self.config.initial_cash,
            "final_equity": float(self.equity[-1]),
            "total_return": self.total_return,
            "max_drawdown": self.max_drawdown,
            "fill_count": len(self.fills),
            "commission": float(self.fills["commission"].sum()),
        }


@dataclass(frozen=True)
class Backtest:
    """Single-instrument, next-open budget simulation; see docs/model.md."""

    data: DailyBars
    initial_cash: float = 100_000.0
    allocation: float = 0.95
    costs: Costs = Costs()

    def run(self, signals: CloseSignals, *, backend: str = "python") -> BacktestResult:
        dates = session_dates(self.data.sessions)
        regime = signals.execution_regime(dates)
        config = Config(
            initial_cash=self.initial_cash,
            entry_weight=self.allocation,
            commission_rate=self.costs.commission_rate,
            minimum_commission=self.costs.minimum_commission,
            slippage_ticks=self.costs.slippage_ticks,
        )
        raw = backtest(self.data, regime, config, backend=backend)
        fills = np.empty(
            len(raw.fills),
            dtype=[
                ("session", "datetime64[D]"),
                ("quantity", "i8"),
                ("price", "f8"),
                ("commission", "f8"),
            ],
        )
        fills["session"] = raw.sessions[raw.fills["session_index"]]
        for field in ("quantity", "price", "commission"):
            fills[field] = raw.fills[field]
        return BacktestResult(
            raw.sessions,
            raw.equity[:, 0],
            raw.cash[:, 0],
            raw.position[:, 0],
            fills,
            raw.blocked[:, 0],
            config,
            raw.backend,
            raw.model,
        )
