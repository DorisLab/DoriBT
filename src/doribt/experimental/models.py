"""Explicit inputs for a single instrument and independent parameter accounts."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import IntEnum

import numpy as np
from numpy.typing import ArrayLike

from .typing import DateArray, FlagArray, FloatArray, IntArray, MarketArrays, RecordArray

MAX_CENTS = 1_000_000_000_000
MAX_TICKS = 1_000_000_000


class BlockReason(IntEnum):
    NONE = 0
    SUSPENDED = 1
    BUY_AT_UPPER_LIMIT = 2
    SELL_AT_LOWER_LIMIT = 3
    INSUFFICIENT_CASH = 4


def scaled(value: float, scale: int, label: str, low: int, high: int) -> int:
    """Convert decimal config values without silently rounding user input."""
    try:
        exact = Decimal(str(value)) * scale
        if not exact.is_finite() or exact != exact.to_integral_value():
            raise ValueError(f"{label} has unsupported precision")
        integer = int(exact)
    except (InvalidOperation, TypeError) as error:
        raise ValueError(f"invalid {label}") from error
    if not low <= integer <= high:
        raise ValueError(f"{label} is outside supported bounds")
    return integer


def session_dates(values: ArrayLike) -> DateArray:
    """Reject ambiguous integer dates and intraday timestamps rather than truncate."""
    raw = np.asarray(values)
    if raw.dtype.kind not in "MUO":
        raise ValueError("sessions must contain calendar dates")
    try:
        parsed = np.asarray(values, dtype="datetime64")
        dates = parsed.astype("datetime64[D]")
    except (ValueError, TypeError) as error:
        raise ValueError("sessions must contain valid calendar dates") from error
    if dates.ndim != 1 or len(dates) == 0 or np.isnat(dates).any():
        raise ValueError("sessions must be non-empty valid dates")
    if (parsed != dates).any():
        raise ValueError("sessions must be whole dates, without intraday timestamps")
    if (np.diff(dates).astype(np.int64) <= 0).any():
        raise ValueError("sessions must be unique and strictly increasing")
    return dates.copy()


@dataclass(frozen=True)
class Config:
    initial_cash: float = 100_000.0
    entry_weight: float = 0.95
    commission_rate: float = 0.0003
    minimum_commission: float = 5.0
    slippage_ticks: int = 1

    def integers(self) -> tuple[int, int, int, int, int]:
        return (
            scaled(self.initial_cash, 100, "initial_cash", 1, MAX_CENTS),
            scaled(self.entry_weight, 1_000_000, "entry_weight", 1, 1_000_000),
            scaled(self.commission_rate, 1_000_000, "commission_rate", 0, 1_000_000),
            scaled(self.minimum_commission, 100, "minimum_commission", 0, MAX_CENTS),
            scaled(self.slippage_ticks, 1, "slippage_ticks", 0, MAX_TICKS),
        )


@dataclass(frozen=True)
class DailyBars:
    sessions: ArrayLike
    open: ArrayLike
    close: ArrayLike
    upper_limit: ArrayLike
    lower_limit: ArrayLike
    suspended: ArrayLike

    def normalized(self) -> tuple[DateArray, MarketArrays]:
        dates = session_dates(self.sessions)
        prices = []
        for name in ["open", "close", "upper_limit", "lower_limit"]:
            values = np.asarray(getattr(self, name), dtype=np.float64)
            if values.shape != dates.shape or not np.isfinite(values).all():
                raise ValueError(f"{name} must have one finite price per session")
            units = np.rint(values * 1000)
            if (units < 1).any() or (units > MAX_TICKS).any():
                raise ValueError(f"{name} is outside supported price bounds")
            if (np.abs(values * 1000 - units) > 1e-6).any():
                raise ValueError(f"{name} must be an exact 0.001 price tick")
            prices.append(np.ascontiguousarray(units, dtype=np.int64))
        op, close, upper, lower = prices
        if (lower > upper).any() or (op < lower).any() or (op > upper).any():
            raise ValueError("open must lie within valid daily price limits")
        if (close < lower).any() or (close > upper).any():
            raise ValueError("close must lie within valid daily price limits")
        suspended = np.asarray(self.suspended)
        if suspended.shape != dates.shape or suspended.dtype.kind != "b":
            raise ValueError("suspended must be a boolean per session")
        return dates, (op, close, upper, lower, np.ascontiguousarray(suspended))


@dataclass(frozen=True)
class Result:
    sessions: DateArray
    equity: FloatArray
    cash: FloatArray
    position: IntArray
    fills: RecordArray
    blocked: FlagArray
    backend: str
    model: str = "etf-next-open-budget-v0"

    def total_return(self, initial_cash: float) -> FloatArray:
        if not np.isfinite(initial_cash) or initial_cash <= 0:
            raise ValueError("initial_cash must be positive and finite")
        return np.asarray(self.equity[-1] / initial_cash - 1, dtype=np.float64)
