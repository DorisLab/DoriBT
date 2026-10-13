"""低换手长区间不按最坏交易数量分配审计缓冲区。"""

from datetime import date, timedelta
from unittest.mock import patch

import numpy as np
import pytest
from test_compiled_fastpath_review import assert_review_parity, review_daily_case

from doribt import (
    Backtest,
    BarExecution,
    Costs,
    Instrument,
    MarketData,
    PositionTargets,
    RuleBook,
    RulePeriod,
    TradingRule,
)
from doribt.kernels.target_loop import simulate_targets

pytestmark = pytest.mark.numba


def test_sparse_daily_audit_capacity_tracks_events():
    calendar = tuple(date(2025, 1, 2) + timedelta(days=i) for i in range(300))
    rule = TradingRule(
        price_tick=".01",
        buy_minimum=100,
        buy_step=100,
        sell_step=100,
        settlement_days=1,
        stamp_duty_sell=0,
        transfer_fee=0,
    )
    data = MarketData.from_records(
        [
            dict(
                session=session,
                symbol="A",
                status="trading",
                open=10,
                close=10,
                high=10,
                low=10,
                volume=100_000,
                upper_limit=None,
                lower_limit=None,
            )
            for session in calendar
        ],
        calendar=calendar,
        instruments=[Instrument(symbol="A", kind="stock")],
        rules=RuleBook(
            (
                RulePeriod(
                    symbol="A",
                    start=calendar[0],
                    end=calendar[-1],
                    rule=rule,
                    source="synthetic",
                    version="1",
                ),
            )
        ),
        source="synthetic sparse daily",
    )
    targets = PositionTargets(sessions=data.timeline, quantities={"A": [100] * len(calendar)})
    captured = []

    def observe(*args):
        arrays = simulate_targets(*args)
        captured.append(arrays)
        return arrays

    test = Backtest(data, execution=BarExecution(), costs=Costs(commission=0, minimum_commission=0))
    with patch("doribt.runtime.compiled_targets.compiled_targets", return_value=observe):
        actual = test.run(targets, backend="numba")
    reference = test.run(lambda ctx: targets(ctx), backend="numba")
    assert_review_parity(actual, reference)
    assert (
        len(actual.orders)
        == len(actual.intents)
        == len(actual.executions)
        == len(actual.tax_lots)
        == 1
    )
    for array in captured[0][4:]:
        assert isinstance(array.base, np.ndarray)
        assert len(array.base) == 16
    assert actual.equity_units[-1] == 1_000_000_000


def test_daily_growth_preserves_dense_records_and_consumed_lot_ids():
    data, quantities = review_daily_case(17)
    targets = PositionTargets(sessions=data.timeline, quantities=quantities)
    captured = []

    def observe(*args):
        arrays = simulate_targets(*args)
        captured.append(arrays)
        return arrays

    test = Backtest(data, execution=BarExecution(participation=1))
    with patch("doribt.runtime.compiled_targets.compiled_targets", return_value=observe):
        actual = test.run(targets, backend="numba")
    reference = test.run(lambda ctx: targets(ctx), backend="numba")
    assert_review_parity(actual, reference)
    assert len(captured[0][5]) > 16
    assert len(captured[0][5].base) > 16
