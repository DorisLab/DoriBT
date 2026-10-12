from dataclasses import fields
from datetime import date
from decimal import Decimal

import numpy as np
import pytest
from corporate_fixtures import distribution, market_with_actions
from minute_fixtures import minute_data

from doribt import Backtest, BarExecution, Costs, Order
from doribt.accounting.account import Account, Lot
from doribt.accounting.rights import RightsBook
from doribt.accounting.taxes import TaxBook
from doribt.kernels.valuation import valuer
from doribt.runtime.broker import Broker
from doribt.runtime.intents import IntentBook
from doribt.runtime.matching import BUDGET, RESERVED
from doribt.runtime.order_state import OrderState
from doribt.validation import MAX_MONEY, integer


def test_account_indexes_follow_nonmonotonic_settlement_and_return_copies():
    account = Account(0, ("A", "B"))
    session = date(2025, 1, 2)
    account.apply_fill("A", 200, session, 100000, 0, 2)
    account.apply_fill("A", 100, session, 100000, 0, 0)
    account.apply_fill("B", 400, session, 100000, 0, 1)
    expected = {0: [100, 0], 1: [100, 400], 2: [300, 400]}
    for index in (2, 0, 1, 2, 1, 0):
        snapshot = account.quantities(index)
        assert snapshot.tolist() == expected[index]
        snapshot[:] = -99
        assert account.quantities(index).tolist() == expected[index]
    total = account.quantities()
    total[:] = 0
    assert account.quantities().tolist() == [300, 400]
    account.apply_fill("A", -100, session, 100000, 0, 0)
    assert account.quantities(0).tolist() == [0, 0]
    assert account.quantities(2).tolist() == [200, 400]
    account.apply_fill("A", -50, session, 100000, 2, 0)
    assert account.quantities().tolist() == [150, 400]
    assert account.lots[0].quantity == 150


def test_registered_overflow_keeps_settled_query_scope():
    account = Account(0, ("A",))
    session = date(2025, 1, 2)
    account.add_lot(Lot("A", 1_000_000_000, session, 0, 1))
    account.add_lot(Lot("A", 1, session, 2, 1))
    assert account.quantities(0).tolist() == [1_000_000_000]
    with pytest.raises(OverflowError, match="registered share quantity"):
        account.quantities()
    with pytest.raises(OverflowError, match="registered share quantity"):
        account.quantities(2)
    account.apply_fill("A", -1, session, 1, 0, 0)
    assert account.quantities().tolist() == [1_000_000_000]


def test_bonus_credit_invalidates_registered_and_settled_indexes():
    action = distribution(
        cash_per_share=0,
        pay_date=None,
        bonus_per_share=1,
        share_credit_date="2025-01-07",
        share_listing_date="2025-01-08",
        taxable_bonus_amount_per_share=0,
    )
    data = market_with_actions([10, 10, 5, 5, 5], [action])
    account = Account(0, data.symbols)
    account.add_lot(Lot("A", 100, data.sessions[0], 0, 100000))
    rights, intents = RightsBook(data), IntentBook()
    rights.close(1, account)
    rights.start(2, account, intents)
    assert rights.pending_shares().tolist() == [100]
    assert account.quantities(3).tolist() == [100]
    rights.start(3, account, intents)
    assert rights.pending_shares().tolist() == [0]
    assert account.quantities().tolist() == [200]
    assert account.quantities(3).tolist() == [100]
    assert account.quantities(4).tolist() == [200]
    assert account.quantities(2).tolist() == [100]


def test_tax_aggregation_preserves_partial_mapping_and_fifo():
    book = TaxBook({"A": "stock", "B": "stock"})
    first, second = date(2025, 1, 2), date(2025, 1, 3)
    book.reconcile(first, {"A": 100, "B": 200})
    book.reconcile(second, {"A": 50})
    assert [(lot.symbol, lot.quantity) for lot in book.lot_records()] == [
        ("A", 50),
        ("B", 200),
    ]
    book.reconcile(second, {})
    assert [lot.quantity for lot in book.lot_records()] == [50, 200]


def test_internal_order_state_preserves_complete_public_snapshot_schema():
    assert [field.name for field in fields(OrderState)] == [field.name for field in fields(Order)]


def test_valuation_preserves_integer_bounds_and_validation_order(backend):
    value = valuer(backend)
    assert value(np.array([10]), np.array([100]), -1000) == 0
    assert value(np.array([0]), np.array([0]), MAX_MONEY) == MAX_MONEY
    assert value(np.array([1]), np.array([1]), MAX_MONEY - 1) == MAX_MONEY
    with pytest.raises(OverflowError, match="account equity"):
        value(np.array([10_000_000_000]), np.array([1_000_000_000]), 0)
    with pytest.raises(OverflowError, match="account equity"):
        value(np.array([1]), np.array([1]), MAX_MONEY)
    with pytest.raises(ValueError, match="delisting"):
        value(np.array([0]), np.array([1]), 0)
    with pytest.raises(OverflowError, match="economic share quantity"):
        value(np.array([0, 1]), np.array([1, 1_000_000_001]), 0)
    with pytest.raises(ValueError):
        value(np.array([1, 1]), np.array([1]), 0)


@pytest.mark.parametrize("value", [False, True, np.bool_(False), np.bool_(True)])
def test_integer_fast_path_does_not_accept_boolean(value):
    with pytest.raises(ValueError, match="quantity: invalid number"):
        integer(value, 1, "quantity", 0, 10)


@pytest.mark.parametrize("value", [2, np.int64(2), 2.0, Decimal("2"), "2"])
def test_integer_fast_path_preserves_exact_scaling_and_boundaries(value):
    result = integer(value, 10000, "amount", 20000, 20000)
    assert result == 20000 and type(result) is int
    with pytest.raises(ValueError, match="amount: outside supported bounds"):
        integer(value, 10000, "amount", 0, 19999)
    with pytest.raises(ValueError, match="amount: outside supported bounds"):
        integer(value, 10000, "amount", 20001, 30000)


def test_integer_fast_path_preserves_large_and_negative_exact_arithmetic():
    large = 10**100 + 123
    assert integer(large, 10000, "large", 0, large * 10000) == large * 10000
    assert integer(-3, 100, "signed", -300, 0) == -300
    assert integer(0, 10000, "zero", 0, 0) == 0
    with pytest.raises(ValueError, match="large: outside supported bounds"):
        integer(10**1000, 10000, "large", 0, MAX_MONEY)


@pytest.mark.parametrize(
    "value", [0.1, Decimal("0.1"), "0.1", float("nan"), float("inf"), "-Infinity"]
)
def test_integer_fast_path_keeps_fractional_and_nonfinite_rejection(value):
    with pytest.raises(ValueError, match="non-finite number or unsupported precision"):
        integer(value, 1, "quantity", 0, 100)


def test_integer_subclasses_retain_existing_string_conversion():
    class StringNumber(int):
        def __str__(self):
            return "1.25"

        def __mul__(self, other):
            raise AssertionError("整数子类必须走原有字符串解析")

    assert integer(StringNumber(9), 100, "amount", 0, 1000) == 125
    with pytest.raises(ValueError, match="unsupported precision"):
        integer(StringNumber(9), 1, "amount", 0, 1000)


def test_reservation_indexes_match_active_orders_through_lifecycle(backend, monkeypatch):
    original = Broker._reservations
    updates = []

    def checked(broker, item, cash, shares):
        original(broker, item, cash, shares)
        assert broker.frozen_cash == sum(int(o.values[BUDGET]) for o in broker.active.values())
        expected = [0] * len(broker.data.symbols)
        for order in broker.active.values():
            expected[order.column] += int(order.values[RESERVED])
        assert [broker.frozen_shares(i) for i in range(len(expected))] == expected
        assert broker.frozen_cash >= 0 and min(expected) >= 0
        updates.append((broker.frozen_cash, tuple(expected)))

    monkeypatch.setattr(Broker, "_reservations", checked)
    data = minute_data(days=2, frequency="5min", volume=100, settlement=0, symbols=("A", "B"))
    snapshots = []

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 500, valid_for="day")
            ctx.order("B", 500, valid_for="day")
            snapshots.append(ctx.orders)
        elif ctx.bar_index == 2:
            snapshots.append(ctx.orders)
            ctx.cancel_order(2)
            snapshots.append(ctx.orders)
            ctx.order("A", -200, valid_for="day")
            ctx.order("A", -100, valid_for="day")
        elif ctx.bar_index == 3:
            ctx.cancel_order(4)
        elif ctx.bar_index == 47:
            ctx.order("B", 500, valid_for="day", limit_price=9)
        elif ctx.bar_index == 95:
            ctx.order("A", 100)

    result = Backtest(
        data,
        initial_cash=20000,
        costs=Costs(commission=0, minimum_commission=0),
        execution=BarExecution(participation=1),
    ).run(strategy, backend=backend)
    assert len(updates) > 15
    assert any(order.status == "cancelled" for order in result.orders)
    assert any(order.status == "expired" for order in result.orders)
    assert result.orders[-1].status == "unexecuted"
    assert snapshots[0][0].filled == 0 and snapshots[0][0].state == "accepted"
    assert snapshots[0][0].frozen_cash_units == 50_000_000
    assert len(snapshots[0]) == 2
    assert snapshots[1][1].filled == 200 and snapshots[1][1].state == "partially_filled"
    assert snapshots[2][1].state == "cancelled"
    assert snapshots[1][1] is not snapshots[2][1]
    assert any(fill.quantity < 0 for fill in result.fills)
    assert np.all(result.reserved_cash_units >= 0)
