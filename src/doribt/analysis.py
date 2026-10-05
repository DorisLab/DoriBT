"""Documented close-to-close research metrics, separate from fixed-point accounting."""

from math import expm1, isfinite, log1p, sqrt
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from .benchmark import Benchmark

if TYPE_CHECKING:
    from .result import BacktestResult

FloatArray = NDArray[np.float64]
Statistics = dict[str, float | int | None]


def returns(equity: FloatArray) -> FloatArray:
    """First close is the baseline; zero/negative denominators are undefined."""
    values = np.full(len(equity), np.nan)
    values[0] = 0.0
    np.divide(equity[1:], equity[:-1], out=values[1:], where=equity[:-1] > 0)
    values[1:] -= 1
    return values


def drawdown(equity: FloatArray, initial: float) -> FloatArray:
    peak = np.maximum.accumulate(np.r_[initial, equity])[1:]
    return 1 - equity / peak


def assumptions(periods_per_year: float | None, risk_free_rate: float) -> None:
    if not isfinite(risk_free_rate) or risk_free_rate <= -1:
        raise ValueError("risk_free_rate must be a finite annual effective rate greater than -1")
    if periods_per_year is None:
        if risk_free_rate != 0:
            raise ValueError("risk_free_rate requires periods_per_year")
    elif (
        isinstance(periods_per_year, bool)
        or not isfinite(periods_per_year)
        or periods_per_year <= 0
    ):
        raise ValueError("periods_per_year must be finite and positive")


def finite(value: float) -> float | None:
    return value if isfinite(value) else None


def _deviation(values: FloatArray) -> float:
    # A truly constant float series has no risk; reduction rounding can leave tiny noise.
    return 0.0 if np.all(values == values[0]) else float(np.std(values, ddof=1))


def _cagr(total_return: float, count: int, periods: float) -> float | None:
    if not count or total_return < -1:
        return None
    if total_return == -1:
        return -1.0
    try:
        return finite(expm1(log1p(total_return) * periods / count))
    except OverflowError:
        return None


def _risk(changes: FloatArray, periods: float | None, rate: float) -> Statistics:
    metrics: Statistics = dict.fromkeys(("annual_volatility", "sharpe", "sortino"))
    if periods is None or len(changes) < 2 or not np.all(np.isfinite(changes)):
        return metrics
    try:
        threshold = expm1(log1p(rate) / periods)
    except OverflowError:
        return metrics
    excess = changes - threshold
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        deviation = _deviation(changes)
        downside = float(np.sqrt(np.mean(np.minimum(excess, 0) ** 2)))
        average = float(np.mean(excess))
        metrics["annual_volatility"] = finite(deviation * sqrt(periods))
        if deviation > 0:
            metrics["sharpe"] = finite(average / deviation * sqrt(periods))
        if downside > 0:
            metrics["sortino"] = finite(average / downside * sqrt(periods))
    return metrics


def _comparison(
    result: "BacktestResult", benchmark: Benchmark, periods: float | None
) -> Statistics:
    benchmark.validate(result.sessions)
    base = benchmark.nav
    total = float(base[-1] - 1)
    stats: Statistics = {
        "benchmark_total_return": total,
        "benchmark_max_drawdown": float(np.max(drawdown(base, 1.0))),
        "excess_total_return": result.total_return - total,
        "beta": None,
        "annual_tracking_error": None,
        "information_ratio": None,
    }
    left, right = result.returns[1:], returns(base)[1:]
    if len(left) < 2 or not np.all(np.isfinite(left)):
        return stats
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        variance = 0.0 if np.all(right == right[0]) else float(np.var(right, ddof=1))
        if variance > 0:
            stats["beta"] = finite(float(np.cov(left, right, ddof=1)[0, 1]) / variance)
        if periods is not None:
            active = left - right
            deviation = _deviation(active)
            stats["annual_tracking_error"] = finite(deviation * sqrt(periods))
            if deviation > 0:
                stats["information_ratio"] = finite(
                    float(np.mean(active)) / deviation * sqrt(periods)
                )
    return stats


def statistics(
    result: "BacktestResult",
    *,
    benchmark: Benchmark | None = None,
    periods_per_year: float | None = None,
    risk_free_rate: float = 0.0,
) -> Statistics:
    assumptions(periods_per_year, risk_free_rate)
    changes = result.returns[1:]
    fills = result.fills
    stats: Statistics = {
        "total_return": result.total_return,
        "max_drawdown": result.max_drawdown,
        "final_equity": float(result.equity[-1]),
        "final_cash": float(result.cash[-1]),
        "fill_count": len(fills),
        "order_count": len(result.orders),
        "unfilled_order_count": sum(order.filled == 0 for order in result.orders),
        "partial_order_count": sum(0 < abs(o.filled) < abs(o.quantity) for o in result.orders),
        "total_fees": sum(
            f.commission_units + f.stamp_duty_units + f.transfer_fee_units for f in fills
        )
        / 10_000,
        "commission": sum(f.commission_units for f in fills) / 10_000,
        "stamp_duty": sum(f.stamp_duty_units for f in fills) / 10_000,
        "transfer_fee": sum(f.transfer_fee_units for f in fills) / 10_000,
        "dividend_tax": sum(tax.amount_units for tax in result.taxes) / 10_000,
        "unpaid_dividend_tax": float(result.tax_payable[-1]),
        "dividend_receivable": float(result.dividend_receivable[-1]),
        "return_periods": len(changes),
        "undefined_return_periods": int(np.count_nonzero(~np.isfinite(changes))),
        "periods_per_year": periods_per_year,
        "risk_free_rate": risk_free_rate,
        "annual_return": None,
    }
    if periods_per_year is not None:
        stats["annual_return"] = _cagr(result.total_return, len(changes), periods_per_year)
    stats.update(_risk(changes, periods_per_year, risk_free_rate))
    if benchmark is not None:
        stats.update(_comparison(result, benchmark, periods_per_year))
    return stats
