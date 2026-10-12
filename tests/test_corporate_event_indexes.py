"""公司行动与税务事件索引保留顺序及延迟付款语义。"""

from datetime import date

import pytest
from corporate_fixtures import distribution, market_with_actions

from doribt.accounting.account import Account, Lot
from doribt.accounting.rights import RightsBook
from doribt.accounting.taxes import TaxBook
from doribt.runtime.intents import IntentBook
from doribt.validation import MAX_MONEY


def test_overdue_settlements_follow_capture_order_not_due_date() -> None:
    first = distribution(
        action_id="first",
        pay_date="2025-01-08",
        bonus_per_share=1,
        share_credit_date="2025-01-07",
        share_listing_date="2025-01-09",
        taxable_bonus_amount_per_share=0,
    )
    second = distribution(action_id="second", symbol="B", pay_date="2025-01-07")
    data = market_with_actions([10] * 6, [second, first], b=[10] * 6)
    account = Account(0, data.symbols)
    account.add_lot(Lot("A", 100, data.sessions[0], 0, 100_000))
    account.add_lot(Lot("B", 100, data.sessions[0], 0, 100_000))
    rights, intents = RightsBook(data), IntentBook()
    rights.close(1, account)
    rights.start(2, account, intents)
    assert rights.receivable == 2_000_000
    snapshot = rights.pending_shares()
    snapshot[:] = 0
    assert rights.pending_shares().tolist() == [100, 0]
    rights.start(4, account, intents)
    assert [(event.action_id, event.kind) for event in rights.events[-3:]] == [
        ("first", "cash_paid"),
        ("first", "shares_credited"),
        ("second", "cash_paid"),
    ]
    assert rights.receivable == 0
    assert rights.pending_shares().tolist() == [0, 0]
    assert account.quantities(4).tolist() == [100, 100]
    assert account.quantities(5).tolist() == [200, 100]
    records = rights.records()
    rights.start(5, account, intents)
    assert rights.records() == records
    assert len(rights.events) == 7


def test_tax_settlement_skips_future_assessment_without_blocking_older_one() -> None:
    book = TaxBook({"A": "stock", "B": "stock"})
    book.reconcile(date(2025, 1, 1), {"A": 100, "B": 100})
    book.attach("A", "future", 1_000_000, date(2025, 1, 1))
    book.attach("B", "older", 1_000_000, date(2025, 1, 1))
    book.reconcile(date(2025, 1, 5), {"A": 0})
    book.reconcile(date(2025, 1, 3), {"B": 0})
    assert book.settle(date(2025, 1, 4), 150_000) == 0
    assert [(payment.action_id, payment.amount_units) for payment in book.payments] == [
        ("older", 150_000)
    ]
    assert book.payable == 250_000
    assert book.settle(date(2025, 1, 6), 225_000) == 0
    assert [(payment.action_id, payment.amount_units) for payment in book.payments] == [
        ("older", 150_000),
        ("future", 200_000),
        ("older", 25_000),
    ]
    assert book.payable == 25_000
    assert [record.action_id for record in book.records()] == ["future", "older"]


def test_tax_symbol_fifo_retains_global_surviving_lot_order() -> None:
    book = TaxBook({"A": "stock", "B": "stock"})
    book.reconcile(date(2025, 1, 1), {"A": 100, "B": 200})
    book.reconcile(date(2025, 1, 2), {"A": 300, "B": 400})
    book.attach("A", "cash", 1_000_000, date(2025, 1, 2))
    book.reconcile(date(2025, 1, 3), {"A": 150})
    assert [(lot.lot_id, lot.symbol, lot.quantity) for lot in book.lot_records()] == [
        (2, "B", 200),
        (3, "A", 150),
        (4, "B", 200),
    ]
    assert book.payable == 300_000
    assert all(not lot.income_micros for lot in book.lots if lot.symbol == "B")


def test_failed_payment_retains_due_event_and_original_error_timing() -> None:
    data = market_with_actions([10] * 5, [distribution()])
    account = Account(MAX_MONEY, data.symbols)
    account.add_lot(Lot("A", 100, data.sessions[0], 0, 100_000))
    rights, intents = RightsBook(data), IntentBook()
    rights.close(1, account)
    rights.start(2, account, intents)
    with pytest.raises(OverflowError, match="dividend payment"):
        rights.start(4, account, intents)
    assert account.cash == MAX_MONEY + 1_000_000
    assert rights.receivable == 1_000_000
    assert not rights.records()[0].cash_paid
    account.cash = 0
    rights.start(4, account, intents)
    assert account.cash == 1_000_000
    assert rights.receivable == 0
    assert rights.records()[0].cash_paid
