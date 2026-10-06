import json
from datetime import date

import pytest
from corporate_fixtures import distribution, market_with_actions
from engine_fixtures import data_for
from minute_fixtures import minute_data
from test_bonus_shares import bonus

from doribt import Backtest, Benchmark, Costs, PositionTargets, RunConfig, WeightTargets

FREE = Costs(commission=0, minimum_commission=0)


def test_moving_average_cost_partial_exits_and_open_position(backend):
    def strategy(ctx):
        quantities = {0: 100, 1: 100, 2: -100, 3: -100}
        if ctx.bar_index in quantities:
            ctx.order("A", quantities[ctx.bar_index])

    # The daily model uses available cash at the next open. BarExecution instead
    # caps this gap-up buy by its prior-close reservation, a separate tested policy.
    costs = Costs(commission=0, minimum_commission=10)
    open_result = Backtest(data_for([10, 10, 12, 14]), initial_cash=10000, costs=costs).run(
        strategy, backend=backend
    )
    report = open_result.report()
    assert report.stats["realized_price_pnl"] == 280
    assert report.stats["unrealized_price_pnl"] == 290
    assert report.stats["total_pnl"] == 570
    assert report.trades.sales[0].cost == 1110
    assert report.trades.positions[0].cost == 1110
    assert report.stats["closed_trade_count"] == 0 and report.stats["win_rate"] is None
    closed_result = Backtest(data_for([10, 10, 12, 14, 15]), initial_cash=10000, costs=costs).run(
        strategy, backend=backend
    )
    closed = closed_result.report()
    assert [sale.price_pnl for sale in closed.trades.sales] == [280, 380]
    assert closed.stats["total_pnl"] == 660
    assert closed.stats["closed_trade_count"] == 1
    assert closed.stats["average_holding_days"] == 5
    assert closed.stats["win_rate"] == 1
    assert closed.stats["profit_factor"] is None
    assert closed.stats["turnover"] == pytest.approx(
        5100 / (10000 + 9990 + 10180 + 10570 + 10660) * 5
    )


def test_two_flat_to_flat_trades_have_independent_win_loss_statistics():
    data = data_for([10, 10, 12, 12, 11])
    result = Backtest(data, costs=FREE).run(
        PositionTargets(sessions=data.sessions, quantities={"A": [100, 0, 100, 0, 0]})
    )
    report = result.report()
    assert [trade.price_pnl for trade in report.trades.closed] == [200, -100]
    assert report.stats["win_rate"] == 0.5
    assert report.stats["payoff_ratio"] == 2
    assert report.stats["profit_factor"] == 2
    assert report.stats["average_holding_days"] == 2


@pytest.mark.parametrize("close", [False, True])
def test_cash_distributions_and_assessed_tax_reconcile_without_double_counting(backend, close):
    data = market_with_actions([10, 10, 9, 9, 9], [distribution()])
    result = Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [1, 0, 0, 0, 0] if close else [1] * 5}),
        backend=backend,
    )
    report = result.report()
    assert report.stats["dividend_income"] == 1000
    assert report.stats["total_pnl"] == (-200 if close else 0)
    assert report.stats["dividend_tax"] == (200 if close else 0)
    assert report.stats["realized_price_pnl"] == (-1000 if close else 0)
    assert report.stats["unrealized_price_pnl"] == (0 if close else -1000)


@pytest.mark.parametrize("length", [3, 5])
def test_bonus_shares_enter_economic_cost_before_credit(backend, length):
    data = market_with_actions([10, 10, 5, 5, 5][:length], [bonus()])
    result = Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [1] * length}), backend=backend
    )
    report = result.report()
    position = report.trades.positions[0]
    assert position.quantity == 2000 and position.cost == 10000
    assert position.market_value == 10000
    assert report.stats["total_pnl"] == 0


def test_taxable_bonus_sold_in_fragments_reconciles(backend):
    action = bonus(
        cash_per_share=1,
        pay_date="2025-01-08",
        bonus_per_share=".5",
        taxable_bonus_amount_per_share=".5",
    )
    data = market_with_actions([10, 10, 6, 6, 6], [action])
    result = Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [1, 0, 0, 0, 0]}), backend=backend
    )
    report = result.report()
    assert report.stats["realized_price_pnl"] == -1000
    assert report.stats["dividend_income"] == 1000
    assert report.stats["dividend_tax"] == 300
    assert report.stats["total_pnl"] == -300


def test_minute_report_includes_first_day_fee_and_accepts_daily_benchmark(tmp_path, backend):
    data = minute_data(days=2, frequency="5min")
    result = Backtest(data, config=RunConfig(backend=backend)).run(
        lambda ctx: ctx.order("A", 100, valid_for="day") if ctx.bar_index == 0 else None
    )
    reference = Benchmark(sessions=data.sessions, prices=[10, 11], name="daily", source="test")
    report = result.report(benchmark=reference)
    assert len(report.daily) == 2
    assert report.stats["return_periods"] == 2
    assert report.stats["periods_per_year"] == 252
    assert report.daily[0].return_rate == pytest.approx(-5 / 100000)
    assert report.daily[1].return_rate == 0
    assert report.stats["annual_return"] == pytest.approx((99995 / 100000) ** 126 - 1)
    assert report.stats["benchmark_total_return"] == pytest.approx(0.1)
    assert result.stats()["annual_return"] is None
    exported = result.export(tmp_path / "daily", daily=True, benchmark=reference)
    saved = json.loads((exported / "report.json").read_text(encoding="utf-8"))
    assert saved["definitions"]["frequency"] == "1d"
    assert saved["daily"][0]["session"] == "2025-01-02"
    assert len(saved["daily"]) == 2
    assert saved["stats"]["return_periods"] == 2
    assert json.loads((exported / "stats.json").read_text())["return_periods"] == 2
    with pytest.raises(ValueError, match="exactly match"):
        result.report(
            benchmark=Benchmark(sessions=[date(2024, 1, 1)], prices=[1], name="x", source="x")
        )


def test_month_returns_daily_risk_and_alpha_are_hand_calculated():
    data = market_with_actions(
        [10, 10, 12, 9, 10.8],
        [],
        dates=["2025-01-30", "2025-01-31", "2025-02-03", "2025-02-04", "2025-02-05"],
    )
    result = Backtest(data, initial_cash=10000, costs=FREE).run(
        WeightTargets(sessions=data.sessions, weights={"A": [1] * 5})
    )
    benchmark = Benchmark(sessions=data.sessions, prices=[10, 10, 11, 11, 11], name="x", source="x")
    report = result.report(benchmark=benchmark, periods_per_year=5)
    assert [row.month for row in report.monthly] == ["2025-01", "2025-02"]
    assert [row.return_rate for row in report.monthly] == pytest.approx([0, 0.08])
    assert report.stats["annual_return"] == pytest.approx(0.08)
    assert report.stats["beta"] == pytest.approx(17 / 8)
    assert report.stats["alpha"] == pytest.approx(-0.0625)
    assert report.stats["max_drawdown"] == pytest.approx(0.25)
    assert report.stats["max_drawdown_duration_days"] == 2


def test_flat_report_has_explicit_missing_trade_and_risk_metrics():
    report = Backtest(data_for([10])).run(lambda ctx: None).report()
    assert report.stats["total_pnl"] == 0
    assert report.stats["annual_return"] == 0
    assert report.stats["sharpe"] is None
    assert report.stats["win_rate"] is None
    assert report.stats["payoff_ratio"] is None
    assert report.monthly[0].return_rate == 0
