"""A daily research report with explicit definitions and composable outputs."""

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from math import expm1, isclose, log1p
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import numpy as np

from doribt.reporting.analysis import Statistics, assumptions, finite
from doribt.reporting.benchmark import Benchmark
from doribt.reporting.daily import (
    DailyAccount,
    MonthlyReturn,
    daily_benchmark,
    daily_result,
    monthly_returns,
)
from doribt.reporting.trades import TradeAnalysis, analyze_trades
from doribt.serialization import encode

if TYPE_CHECKING:
    from doribt.reporting.result import BacktestResult


@dataclass(frozen=True)
class ResearchReport:
    stats: Mapping[str, float | int | None]
    daily: tuple[DailyAccount, ...]
    monthly: tuple[MonthlyReturn, ...]
    trades: TradeAnalysis
    definitions: Mapping[str, object]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema": "doribt.report/1",
            "stats": dict(self.stats),
            "daily": [asdict(row) for row in self.daily],
            "monthly": [asdict(row) for row in self.monthly],
            "trades": self.trades.to_dict(),
            "definitions": dict(self.definitions),
        }
        result: dict[str, Any] = json.loads(encode(payload))
        return result


def _duration(drawdown: np.ndarray[Any, np.dtype[np.float64]]) -> int:
    longest = current = 0
    for value in drawdown:
        current = current + 1 if value > 0 else 0
        longest = max(longest, current)
    return longest


def _alpha(
    daily: "BacktestResult", base: Benchmark, stats: Statistics, periods: float, rate: float
) -> None:
    stats["alpha"] = None
    beta = stats["beta"]
    changes = daily.returns[1:]
    if beta is None or not np.all(np.isfinite(changes)):
        return
    reference = np.diff(base.nav) / base.nav[:-1]
    threshold = expm1(log1p(rate) / periods)
    value = float(np.mean(changes - threshold) - beta * np.mean(reference - threshold)) * periods
    stats["alpha"] = finite(value)


def report(
    result: "BacktestResult",
    *,
    benchmark: Benchmark | None,
    periods_per_year: float,
    risk_free_rate: float,
) -> ResearchReport:
    assumptions(periods_per_year, risk_free_rate)
    daily = daily_result(result)
    base = daily_benchmark(result, benchmark) if benchmark is not None else None
    stats = daily.stats(
        benchmark=base, periods_per_year=periods_per_year, risk_free_rate=risk_free_rate
    )
    trades = analyze_trades(result)
    stats.update(trades.stats())
    if not isclose(
        float(stats["total_pnl"] or 0),
        result.equity[-1] - result.initial_cash,
        rel_tol=1e-10,
        abs_tol=0.00001,
    ):
        raise ValueError("price PnL, distributions and taxes do not reconcile to account equity")
    turnover = sum(abs(fill.quantity) * fill.price_units / 10_000 for fill in result.fills)
    mean_equity = float(np.mean(daily.equity[1:]))
    stats["turnover"] = turnover / mean_equity if mean_equity > 0 else None
    stats["max_drawdown_duration_days"] = _duration(daily.drawdown[1:])
    if base is not None:
        _alpha(daily, base, stats, periods_per_year, risk_free_rate)
    returns, drawdowns, equities, cash = daily.returns, daily.drawdown, daily.equity, daily.cash
    nav, base_nav = daily.nav, None if base is None else base.nav
    rows = tuple(
        DailyAccount(
            session,
            float(equities[i]),
            float(cash[i]),
            float(nav[i]),
            finite(float(returns[i])),
            float(drawdowns[i]),
            None if base_nav is None else float(base_nav[i]),
        )
        for i, session in enumerate(daily.sessions)
        if i
    )
    definitions = {
        "frequency": "1d",
        "sampling": "last_supplied_bar_of_each_trading_day",
        "return_baseline": "initial_cash_including_first_day_pnl",
        "periods_per_year": periods_per_year,
        "risk_free_rate": risk_free_rate,
        "cost_basis": "moving_average_including_buy_fees",
        "trade": "symbol_flat_to_flat_including_pending_bonus_shares",
        "trade_pnl": "price_pnl_after_transaction_fees_excluding_cash_dividends_and_dividend_tax",
        "holding_days": "calendar_days",
        "drawdown_duration_days": "consecutive_underwater_trading_days",
        "turnover": "cumulative_two_sided_notional_divided_by_mean_daily_equity",
        "alpha": "daily_CAPM_intercept_times_periods_per_year",
        "benchmark_baseline": "first_supplied_price; no assumed preceding close",
    }
    return ResearchReport(
        MappingProxyType(stats), rows, monthly_returns(rows), trades, MappingProxyType(definitions)
    )
