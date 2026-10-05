"""Hand-calculated curves and explicitly undefined metric cases."""

from dataclasses import replace
from math import sqrt

import numpy as np
import pytest
from engine_fixtures import data_for

from doribt import Backtest, Benchmark, Costs, WeightTargets

FREE = Costs(commission=0, minimum_commission=0)


def curve():
    data = data_for([10, 10, 12, 9, 10.8])
    return Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [1] * 5})
    )


def test_hand_calculated_risk_and_baseline_exclusion():
    result = curve()
    np.testing.assert_allclose(result.nav, [1, 1, 1.2, 0.9, 1.08])
    np.testing.assert_allclose(result.returns, [0, 0, 0.2, -0.25, 0.2])
    np.testing.assert_allclose(result.drawdown, [0, 0, 0, 0.25, 0.1])
    # Four observed intervals, sample variance over [0, .2, -.25, .2].
    mean = 0.15 / 4
    variance = ((0 - mean) ** 2 + 2 * (0.2 - mean) ** 2 + (-0.25 - mean) ** 2) / 3
    stats = result.stats(periods_per_year=4)
    assert stats["annual_return"] == pytest.approx(0.08)
    assert stats["annual_volatility"] == pytest.approx(sqrt(variance) * 2)
    assert stats["sharpe"] == pytest.approx(mean / sqrt(variance) * 2)
    assert stats["sortino"] == pytest.approx(mean / sqrt(0.25**2 / 4) * 2)
    assert stats["return_periods"] == 4
    assert stats["fill_count"] == 1
    assert result.stats()["annual_volatility"] is None
    assert result.stats()["annual_return"] is None
    # Effective annual 46.41% => per-period 10% with four periods a year.
    adjusted = result.stats(periods_per_year=4, risk_free_rate=0.4641)
    assert adjusted["sharpe"] == pytest.approx((mean - 0.1) / sqrt(variance) * 2)
    assert adjusted["sortino"] == pytest.approx((mean - 0.1) / sqrt((0.1**2 + 0.35**2) / 4) * 2)


def test_exact_benchmark_alignment_and_independent_relative_metrics():
    result = curve()
    reference = Benchmark(
        sessions=result.sessions,
        prices=[10, 10, 11, 11, 11],
        name="Fictional price index",
        source="hand calculation",
    )
    stats = result.stats(benchmark=reference, periods_per_year=4)
    assert stats["benchmark_total_return"] == pytest.approx(0.1)
    assert stats["excess_total_return"] == pytest.approx(-0.02)
    # Benchmark returns [0,.1,0,0], covariance .0054166667 / variance .0025.
    assert stats["beta"] == pytest.approx(13 / 6)
    active = [0, 0.1, -0.25, 0.2]
    mean = sum(active) / 4
    deviation = sqrt(sum((item - mean) ** 2 for item in active) / 3)
    assert stats["annual_tracking_error"] == pytest.approx(2 * deviation)
    assert stats["information_ratio"] == pytest.approx(mean / deviation * 2)
    assert result.stats(benchmark=reference)["annual_tracking_error"] is None
    wrong = Benchmark(sessions=result.sessions[:-1], prices=[1] * 4, name="x", source="x")
    for operation in (result.stats, result.plot):
        with pytest.raises(ValueError, match="exactly match"):
            operation(benchmark=wrong)


def test_one_close_flat_zero_denominator_and_overflow_are_explicit():
    empty = Backtest(data_for([10]), costs=FREE).run(lambda ctx: None)
    assert empty.stats(periods_per_year=252)["annual_return"] is None
    assert empty.stats()["return_periods"] == 0
    flat = Backtest(data_for([10] * 5), costs=FREE).run(lambda ctx: None)
    stats = flat.stats(periods_per_year=252)
    assert stats["annual_volatility"] == 0
    assert stats["sharpe"] is None and stats["sortino"] is None
    benchmark = Benchmark(sessions=flat.sessions, prices=[1] * 5, name="flat", source="test")
    comparison = flat.stats(benchmark=benchmark, periods_per_year=252)
    assert comparison["beta"] is None and comparison["information_ratio"] is None
    assert comparison["annual_tracking_error"] == 0
    insolvent = replace(flat, equity_units=np.array([100000000, 100000000, 0, 0, 0]))
    stats = insolvent.stats(periods_per_year=252)
    assert stats["max_drawdown"] == 1
    assert stats["annual_return"] == -1
    assert stats["undefined_return_periods"] == 2
    assert stats["sharpe"] is None and stats["annual_volatility"] is None
    extreme = curve().stats(periods_per_year=1e308, risk_free_rate=0)
    assert extreme["annual_return"] is None


@pytest.mark.parametrize(
    "periods,rate",
    [(0, 0), (-1, 0), (True, 0), (float("inf"), 0), (None, 0.03), (252, -1), (252, float("nan"))],
)
def test_invalid_metric_assumptions_fail(periods, rate):
    with pytest.raises(ValueError):
        curve().stats(periods_per_year=periods, risk_free_rate=rate)


@pytest.mark.parametrize(
    "prices",
    [[1, 2], [1, 0, 1], [1, float("nan"), 1], [1, float("inf"), 1], [1, -1, 1], [1e-300, 1e300, 1]],
)
def test_benchmark_rejects_invalid_prices(prices):
    with pytest.raises(ValueError):
        Benchmark(sessions=data_for([10] * 3).sessions, prices=prices, name="x", source="x")


def test_benchmark_snapshots_input_and_requires_identity():
    values = [1.0, 2.0, 3.0]
    sessions = data_for([10] * 3).sessions
    benchmark = Benchmark(sessions=sessions, prices=values, name="test", source="public")
    values[0] = 9
    assert benchmark.nav.tolist() == [1, 2, 3]
    with pytest.raises(ValueError, match="name and source"):
        Benchmark(sessions=sessions, prices=values, name=" ", source="public")
