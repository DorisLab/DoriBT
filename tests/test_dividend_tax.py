from datetime import date

import pytest

from doribt.taxes import TaxBook, anniversary, dividend_rate, validate_tax_period


@pytest.mark.parametrize(
    "acquired,sold,rate",
    [
        ("2024-01-08", "2024-02-08", 200_000),
        ("2024-01-08", "2024-02-09", 100_000),
        ("2024-01-08", "2025-01-08", 100_000),
        ("2024-01-08", "2025-01-09", 0),
        ("2024-01-31", "2024-02-29", 200_000),
        ("2024-01-31", "2024-03-01", 100_000),
        ("2023-01-31", "2023-02-28", 200_000),
        ("2023-01-31", "2023-03-01", 100_000),
        ("2024-02-29", "2025-02-28", 100_000),
        ("2024-02-29", "2025-03-01", 0),
    ],
)
def test_calendar_month_and_year_are_not_30_or_365_days(acquired, sold, rate):
    assert dividend_rate(date.fromisoformat(acquired), date.fromisoformat(sold)) == rate


def test_fifo_tax_has_three_holding_periods_and_partial_disposal():
    book = TaxBook({"A": "stock"})
    book.reconcile(date(2024, 1, 1), {"A": 100})
    book.reconcile(date(2024, 6, 1), {"A": 200})
    book.reconcile(date(2024, 12, 20), {"A": 300})
    book.attach("A", "dividend", 1_000_000, date(2024, 12, 20))
    book.reconcile(date(2025, 1, 6), {"A": 50})
    # 100 exempt + 100 * 1 yuan * 10% + 50 * 1 yuan * 20% = 20 yuan.
    assert book.payable == 200_000
    assert book.lot_records()[0].quantity == 50
    assert book.lot_records()[0].acquired == date(2024, 12, 20)
    assert book.settle(date(2025, 1, 6), 500_000) == 500_000  # Not yet due.
    assert book.settle(date(2025, 1, 7), 100_000) == 0
    assert book.payable == 100_000
    assert book.settle(date(2025, 1, 8), 150_000) == 50_000
    assert book.payable == 0
    assert [payment.amount_units for payment in book.payments] == [100_000, 100_000]


def test_separate_events_keep_income_and_zero_tax_explanations():
    book = TaxBook({"A": "stock"})
    book.reconcile(date(2024, 1, 2), {"A": 100})
    book.attach("A", "first", 1_000_000, date(2024, 2, 1))
    book.attach("A", "second", 2_000_000, date(2024, 6, 1))
    book.reconcile(date(2025, 1, 3), {"A": 0})
    assert len(book.records()) == 2
    assert all(record.amount_units == 0 for record in book.records())
    assert not book.lot_records()


def test_policy_and_time_fail_closed():
    with pytest.raises(ValueError, match="outside the verified"):
        validate_tax_period(date(2015, 9, 8))
    with pytest.raises(ValueError, match="outside the verified"):
        validate_tax_period(date(2027, 1, 1))
    with pytest.raises(ValueError, match="precede acquisition"):
        dividend_rate(date(2025, 1, 2), date(2025, 1, 1))
    assert anniversary(date(2025, 12, 31), 1) == date(2026, 1, 31)


def test_future_disposal_cannot_silently_extend_verified_tax_policy():
    book = TaxBook({"A": "stock"})
    book.reconcile(date(2025, 1, 2), {"A": 100})
    book.attach("A", "dividend", 1_000_000, date(2025, 1, 3))
    with pytest.raises(ValueError, match="outside the verified"):
        book.reconcile(date(2027, 1, 4), {"A": 0})
