from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest
from minute_fixtures import minute_data

from doribt import Backtest, CorporateAction, Costs, MarketData, WeightTargets

FREE = Costs(commission=0, minimum_commission=0)


def test_minute_dividend_record_ex_payment_and_share_credit_happen_once(backend):
    action = CorporateAction(
        action_id="bonus",
        symbol="A",
        kind="distribution",
        announced="2025-01-02",
        record_date="2025-01-02",
        ex_date="2025-01-03",
        pay_date="2025-01-03",
        share_credit_date="2025-01-03",
        share_listing_date="2025-01-06",
        cash_per_share=1,
        bonus_per_share=1,
        taxable_bonus_amount_per_share=0,
        source="synthetic lifecycle",
    )
    data = minute_data(days=3, volume=100000, actions=(action,))
    result = Backtest(data, costs=FREE).run(
        lambda ctx: ctx.order("A", 100) if ctx.bar_index == 0 else None, backend=backend
    )
    assert len(result.entitlements) == 1
    assert [event.kind for event in result.corporate_events] == [
        "recorded",
        "accrued",
        "cash_paid",
        "shares_credited",
    ]
    assert result.holdings[239, 0] == 100
    assert np.all(result.holdings[240:, 0] == 200)
    assert np.all(result.sellable[240:480, 0] == 100)
    assert np.all(result.sellable[480:, 0] == 200)
    assert result.cash[-1] == 99100


def test_day_order_expiry_and_target_replacement_release_reservations(backend):
    snapshots = []

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.target_positions({"A": 1000})
        if ctx.bar_index == 2:
            snapshots.extend(ctx.orders)
            ctx.target_positions({"A": 200})

    result = Backtest(minute_data(), costs=FREE).run(strategy, backend=backend)
    assert result.orders[0].status == "cancelled"
    assert result.orders[0].filled == 100
    assert result.holdings[-1, 0] == 200
    assert snapshots[0].status == "partially_filled"
    assert snapshots[0].filled == 100
    assert result.intents[0].reason == "target_replaced"


def test_partial_target_survives_to_next_day(backend):
    result = Backtest(minute_data(volume=1000), costs=FREE).run(
        lambda ctx: ctx.target_positions({"A": 1000}) if ctx.bar_index == 237 else None,
        backend=backend,
    )
    assert [o.quantity for o in result.orders] == [1000, 900]
    assert [o.filled for o in result.orders] == [100, 900]
    assert result.intents[0].status == "fulfilled"


def test_sell_reservations_and_shared_capacity_do_not_allow_shorting(backend):
    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 100, valid_for="day")
        if ctx.bar_index == 240:
            ctx.order("A", -100, valid_for="day")
            ctx.order("A", -100, valid_for="day")

    result = Backtest(minute_data(), costs=FREE).run(strategy, backend=backend)
    assert result.holdings.min() == 0
    assert [o.filled for o in result.orders] == [100, -100, 0]
    assert result.orders[-1].status == "expired"


def test_shared_cash_rotation_can_use_same_bar_sale_proceeds(backend):
    data = minute_data(symbols=("A", "B"), volume=100000)

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.target_positions({"B": 1000})
        if ctx.bar_index == 240:
            ctx.target_positions({"A": 1000, "B": 0})

    result = Backtest(data, initial_cash=10000, costs=FREE).run(strategy, backend=backend)
    assert [(fill.symbol, fill.quantity) for fill in result.fills] == [
        ("B", 1000),
        ("B", -1000),
        ("A", 1000),
    ]
    assert result.fills[1].timestamp == result.fills[2].timestamp
    assert result.holdings[-1].tolist() == [1000, 0]
    assert result.cash[-1] == 0


def test_minute_sales_create_one_daily_dividend_tax_assessment(backend):
    action = CorporateAction(
        action_id="cash",
        symbol="A",
        kind="distribution",
        announced="2025-01-02",
        record_date="2025-01-02",
        ex_date="2025-01-03",
        pay_date="2025-01-03",
        cash_per_share=1,
        source="synthetic dividend",
    )
    data = minute_data(days=3, volume=100000, actions=(action,))

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 100)
        if ctx.bar_index == 240:
            ctx.order("A", -100)

    result = Backtest(data, costs=FREE).run(strategy, backend=backend)
    assert result.cash[-1] == 100080
    assert sum(record.amount_units for record in result.taxes) == 200000
    assert len(result.taxes) == 1 and len(result.tax_payments) == 1


def test_next_bar_suspension_expires_order_but_day_retries(backend):
    data = minute_data(changes={1: {"status": "suspended", "volume": 0}})

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 100)
            ctx.order("A", 100, valid_for="day")

    result = Backtest(data, costs=FREE).run(strategy, backend=backend)
    assert result.orders[0].reason == "suspended"
    assert result.orders[0].status == "expired"
    assert result.orders[1].filled == 100
    assert result.fills[0].timestamp == data.timeline[2]


def test_partial_sales_can_raise_cash_when_tax_exceeds_each_fill(backend):
    action = CorporateAction(
        action_id="owed",
        symbol="A",
        kind="distribution",
        announced="2025-01-02",
        record_date="2025-01-02",
        ex_date="2025-01-03",
        pay_date="2025-01-10",
        cash_per_share=1,
        source="synthetic unpaid dividend tax",
    )
    data = minute_data(
        days=3,
        symbols=("A", "B"),
        volume=100000,
        actions=(action,),
        changes={i * 2 + 1: {"volume": 20} for i in range(480, 720)},
    )
    observed = []

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.target_positions({"A": 1000})
        elif ctx.bar_index == 240:
            ctx.target_positions({"A": 0, "B": 1000})
        elif ctx.bar_index == 479:
            ctx.order("B", -100, valid_for="day")
        elif ctx.bar_index == 480:
            observed.append((ctx.account.cash, ctx.account.tax_payable, ctx.account.available_cash))

    result = Backtest(data, initial_cash=10000, costs=FREE).run(strategy, backend=backend)
    assert observed == [(10, 200, 0)]
    assert result.fills[3].quantity == -1
    assert result.fills[3].timestamp == data.timeline[480]
    assert result.orders[-1].filled == -100
    assert result.cash[-1] == 1000 and result.tax_payable[-1] == 200


def test_five_minute_history_and_final_order_are_identified():
    data = minute_data(frequency="5min")
    assert len(data.timeline) == 96
    observed = []

    def strategy(ctx):
        assert ctx.session == ctx.now.date()
        if ctx.bar_index == 95:
            observed.append(len(ctx.history("A")))
            ctx.order("A", 100)

    result = Backtest(data).run(strategy)
    assert observed == [96]
    assert result.orders[0].status == "unexecuted"
    assert result.run_info.to_dict()["data"]["frequency"] == "5min"
    assert not result.fills


def test_missing_duplicate_offgrid_and_mixed_data_are_rejected():
    data = minute_data()
    with pytest.raises(ValueError, match="missing"):
        replace(data, bars=data.bars[1:])
    with pytest.raises(ValueError, match="duplicate"):
        replace(data, bars=(data.bars[0], *data.bars))
    offgrid = replace(data.bars[0], timestamp=data.bars[0].timestamp - timedelta(minutes=1))
    with pytest.raises(ValueError, match="unexpected"):
        replace(data, bars=(offgrid, *data.bars[1:]))
    with pytest.raises(ValueError, match="mixed"):
        replace(data, clock=None)
    with pytest.raises(ValueError, match="offset"):
        replace(data.bars[0], timestamp=data.bars[0].timestamp.replace(tzinfo=None))
    with pytest.raises(ValueError, match="exactly match"):
        Backtest(data).run(WeightTargets(sessions=data.sessions, weights={"A": [0, 0]}))


def test_explicit_minute_columns_and_price_cutoff():
    data = minute_data()
    with pytest.raises(ValueError, match="timestamp and phase"):
        MarketData.from_minutes(
            [{}],
            calendar=data.sessions,
            instruments=data.instruments,
            rules=data.rules,
            source="test",
        )
    assert data.prices("close", as_of=data.timeline[10]).shape == (11, 1)
    with pytest.raises(ValueError, match="offset"):
        data.prices("close", as_of="2025-01-02")


def test_minute_export_preserves_many_fills_and_reservations(tmp_path):
    import csv
    import json

    result = Backtest(minute_data()).run(
        lambda ctx: ctx.order("A", 1000, valid_for="day") if ctx.bar_index == 0 else None
    )
    output = result.export(tmp_path / "report")
    ledger = json.loads((output / "ledger.json").read_text())
    assert len(ledger["orders"]) == 1
    assert len(ledger["fills"]) == 20
    with (output / "account.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert int(rows[1]["frozen_cash_units"]) == result.frozen_cash_units[1]
    assert (
        int(rows[1]["available_cash_units"]) + int(rows[1]["frozen_cash_units"])
        == result.cash_units[1]
    )
