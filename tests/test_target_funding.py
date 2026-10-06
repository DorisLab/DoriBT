import json
from decimal import Decimal

import numpy as np
import pytest
from engine_fixtures import data_for
from minute_fixtures import minute_data
from test_scheduled import compare

from doribt import Backtest, BarExecution, Costs, PositionTargets, RunConfig

FREE = Costs(commission=0, minimum_commission=0)


@pytest.mark.parametrize("mode", ["order", "target"])
@pytest.mark.parametrize("price,remaining", [(10.2, 4900), (9.8, 5100)])
def test_fixed_shares_use_free_cash_across_price_gaps(backend, mode, price, remaining):
    data = data_for([10, price, price])

    def strategy(ctx):
        if ctx.bar_index == 0:
            if mode == "order":
                ctx.order("A", 500)
            else:
                ctx.target_positions({"A": 500})

    result = Backtest(data, config=RunConfig(initial_cash=10000, costs=FREE)).run(
        strategy, backend=backend
    )
    assert result.holdings[:, 0].tolist() == [0, 500, 500]
    assert result.cash.tolist() == [10000, remaining, remaining]
    assert len(result.fills) == 1
    if mode == "target":
        assert result.intents[0].status == "fulfilled"


def test_explicit_spending_cap_includes_fees_and_survives_partial_fills(backend, tmp_path):
    data = minute_data(days=1, volume=200, changes={i: {"open": 10.2} for i in range(1, 240)})
    costs = Costs(commission=0.001, minimum_commission=5)
    result = Backtest(
        data, initial_cash=10000, costs=costs, execution=BarExecution(participation=1)
    ).run(
        lambda ctx: (
            ctx.order("A", 500, valid_for="day", max_spend=5005) if ctx.bar_index == 0 else None
        ),
        backend=backend,
    )
    # 490 * 10.2 + 5 = 5003；下一股超过明确的 5005 元上限。
    assert [f.quantity for f in result.fills] == [200, 200, 90]
    assert [f.commission for f in result.fills] == [5, 0, 0]
    spent = sum(Decimal(f.quantity) * Decimal("10.2") + Decimal(str(f.fees)) for f in result.fills)
    assert spent == Decimal(5003)
    assert result.cash[-1] == 4997
    assert result.orders[0].remaining == 10
    assert result.orders[0].reason == "spending_limit"
    assert result.orders[0].max_spend_units == 50_050_000
    assert np.all(result.frozen_cash_units >= 0)
    result.export(tmp_path / "report")
    ledger = json.loads((tmp_path / "report/ledger.json").read_text(encoding="utf-8"))
    assert ledger["orders"][0]["max_spend_units"] == 50_050_000


def test_gap_cannot_take_cash_frozen_by_another_order(backend):
    data = data_for([10, 10.2], [10, 10], changes={3: {"status": "suspended", "volume": 0}})

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 500)
            ctx.order("B", 500)

    result = Backtest(data, config=RunConfig(initial_cash=10000, costs=FREE)).run(
        strategy, backend=backend
    )
    assert result.holdings[-1].tolist() == [490, 0]
    assert result.cash[-1] == 5002
    assert result.orders[0].reason == "insufficient_cash"
    assert result.orders[1].reason == "suspended"


def test_unfilled_order_does_not_freeze_all_free_cash_and_cancel_releases_estimate(backend):
    data = minute_data(days=1, volume=10000, changes={1: {"status": "suspended", "volume": 0}})
    seen = []

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 100, valid_for="day")
        elif ctx.bar_index == 1:
            seen.append(ctx.account.frozen_cash)
            ctx.order("A", 500)
            ctx.cancel_order(1)

    result = Backtest(data, initial_cash=10000, costs=FREE).run(strategy, backend=backend)
    assert seen == [1000]
    assert [f.quantity for f in result.fills] == [500]
    assert result.orders[0].state == "cancelled"
    assert result.cash[-1] == 5000


def test_scheduled_scan_finds_fill_above_close_reservation(backend):
    # 先成交 499 股，预留只剩 10 元；空闲资金仍能支付后续 11 元的一股。
    changes = {1: {"volume": 499}, 2: {"volume": 0}, 3: {"open": 11, "volume": 1}}
    data = minute_data(days=1, frequency="5min", volume=0, changes=changes)
    targets = PositionTargets(sessions=data.timeline, quantities={"A": [500] * 48})
    result = compare(
        data,
        targets,
        backend,
        initial_cash=10000,
        costs=FREE,
        execution=BarExecution(participation=1),
    )
    assert [f.quantity for f in result.fills] == [499, 1]
    assert [f.timestamp for f in result.fills] == [data.timeline[1], data.timeline[3]]
    assert result.cash[-1] == 4999
    assert result.intents[0].status == "fulfilled"


@pytest.mark.parametrize("limit", [0, -1, "nan", "inf", "0.00001"])
def test_invalid_spending_limit_fails_before_order_creation(limit):
    def strategy(ctx):
        with pytest.raises(ValueError, match="max_spend"):
            ctx.order("A", 100, max_spend=limit)
        assert ctx.orders == ()

    Backtest(data_for([10, 10]), config=RunConfig()).run(strategy)


def test_spending_limit_requires_buy_and_bar_execution():
    with pytest.raises(RuntimeError, match="buy orders"):
        Backtest(data_for([10, 10]), config=RunConfig()).run(
            lambda ctx: ctx.order("A", -100, max_spend=1000)
        )
    with pytest.raises(RuntimeError, match="BarExecution"):
        Backtest(data_for([10, 10])).run(lambda ctx: ctx.order("A", 100, max_spend=1000))
