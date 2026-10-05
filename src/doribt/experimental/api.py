"""Validated public boundary; acceleration is explicitly selected and reported."""

from functools import cache

import numpy as np

from .kernel import simulate
from .models import Config, DailyBars, Result

FILL_DTYPE = np.dtype(
    [
        ("session_index", "i8"),
        ("account", "i8"),
        ("quantity", "i8"),
        ("price", "f8"),
        ("commission", "f8"),
    ]
)


@cache
def accelerated():
    try:
        from numba import njit
    except ImportError as error:
        raise ImportError("Numba backend requires the 'doribt[numba]' extra") from error
    return njit(cache=True)(simulate)


def backtest(
    bars: DailyBars, regime: np.ndarray, config: Config | None = None, *, backend: str = "python"
) -> Result:
    """Run an already-lagged 0/1 regime; columns are independent accounts."""
    if backend not in {"python", "numba"}:
        raise ValueError("backend must be 'python' or 'numba'")
    config = config or Config()
    dates, arrays = bars.normalized()
    regimes = np.asarray(regime)
    if regimes.ndim == 1:
        regimes = regimes[:, None]
    if regimes.ndim != 2 or regimes.shape[0] != len(dates) or regimes.shape[1] == 0:
        raise ValueError("regime must have one row per session and at least one account")
    if regimes.dtype.kind not in "biuf" or not np.isin(regimes, [0, 1]).all():
        raise ValueError("regime must contain only 0/1 decisions")
    values = np.ascontiguousarray(regimes, dtype=np.int8)
    runner = simulate if backend == "python" else accelerated()
    eq, cash, position, raw, blocked = runner(*arrays, values, *config.integers())
    if len(raw):
        raw = raw[np.lexsort((raw[:, 1], raw[:, 0]))]
    fills = np.empty(len(raw), dtype=FILL_DTYPE)
    for index, field in enumerate(FILL_DTYPE.names):
        fills[field] = (
            raw[:, index] / (1000 if index == 3 else 100) if index >= 3 else raw[:, index]
        )
    return Result(dates, eq / 100, cash / 100, position, fills, blocked, backend)
