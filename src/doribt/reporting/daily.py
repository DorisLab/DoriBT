"""End-of-session sampling with initial cash retained as the first return baseline."""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np

from doribt.reporting.benchmark import Benchmark

if TYPE_CHECKING:
    from doribt.reporting.result import BacktestResult


@dataclass(frozen=True)
class DailyAccount:
    session: date
    equity: float
    cash: float
    nav: float
    return_rate: float | None
    drawdown: float
    benchmark_nav: float | None


@dataclass(frozen=True)
class MonthlyReturn:
    month: str
    return_rate: float | None
    benchmark_return: float | None


def session_date(value: date) -> date:
    return value.date() if isinstance(value, datetime) else value


def daily_indices(result: "BacktestResult") -> tuple[tuple[date, ...], list[int]]:
    last = {session_date(value): i for i, value in enumerate(result.sessions)}
    return tuple(last), list(last.values())


def daily_result(result: "BacktestResult") -> "BacktestResult":
    days, indices = daily_indices(result)
    baseline = days[0] - timedelta(days=1)
    cash = round(result.initial_cash * 10_000)
    return replace(
        result,
        sessions=(baseline, *days),
        outputs={},
        equity_units=np.r_[cash, result.equity_units[indices]],
        cash_units=np.r_[cash, result.cash_units[indices]],
        holdings=np.vstack([np.zeros_like(result.holdings[0]), result.holdings[indices]]),
        sellable=np.vstack([np.zeros_like(result.sellable[0]), result.sellable[indices]]),
        pending_shares=np.vstack(
            [np.zeros_like(result.pending_shares[0]), result.pending_shares[indices]]
        ),
        close_units=np.vstack([result.close_units[0], result.close_units[indices]]),
        dividend_receivable_units=np.r_[0, result.dividend_receivable_units[indices]],
        tax_payable_units=np.r_[0, result.tax_payable_units[indices]],
        reserved_cash_units=np.r_[0, result.frozen_cash_units[indices]],
        reserved_shares=np.vstack(
            [np.zeros_like(result.holdings[0]), result.frozen_shares[indices]]
        ),
    )


def daily_benchmark(result: "BacktestResult", benchmark: Benchmark) -> Benchmark:
    days, indices = daily_indices(result)
    values = np.asarray(benchmark.prices, dtype=np.float64)
    if tuple(benchmark.sessions) == result.sessions:
        prices = values[indices].tolist()
    elif tuple(benchmark.sessions) == days:
        prices = values.tolist()
    else:
        raise ValueError("benchmark sessions must exactly match bars or trading days")
    return Benchmark(
        sessions=(days[0] - timedelta(days=1), *days),
        prices=[float(values[0]), *prices],
        name=benchmark.name,
        source=benchmark.source,
    )


def monthly_returns(rows: tuple[DailyAccount, ...]) -> tuple[MonthlyReturn, ...]:
    ends = {row.session.strftime("%Y-%m"): row for row in rows}
    prior, base = 1.0, 1.0
    months = []
    for month, row in ends.items():
        relative = None if row.benchmark_nav is None else row.benchmark_nav / base - 1
        months.append(MonthlyReturn(month, row.nav / prior - 1 if prior > 0 else None, relative))
        prior = row.nav
        if row.benchmark_nav is not None:
            base = row.benchmark_nav
    return tuple(months)
