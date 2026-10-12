"""数值持仓批次与独立 Python FIFO 账本核对。"""

from datetime import date, timedelta

import numpy as np
import pytest

from doribt.accounting.account import Account, Lot

DAY = date(2025, 1, 2)


def test_fifo_skips_unsettled_and_preserves_acquisition_order() -> None:
    account = Account(10_000, ("A", "B"))
    account.add_lot(Lot("A", 100, DAY, 4, 1))
    account.add_lot(Lot("B", 70, DAY, 0, 2))
    account.add_lot(Lot("A", 200, DAY, 1, 3))
    account.add_lot(Lot("A", 300, DAY, 0, 4))
    account.apply_fill("A", -250, DAY, 5, 1, 0)
    assert [(lot.symbol, lot.quantity, lot.price_units) for lot in account.lots] == [
        ("A", 100, 1),
        ("B", 70, 2),
        ("A", 250, 4),
    ]
    assert account.quantities().tolist() == [350, 70]
    assert account.quantities(0).tolist() == [250, 70]
    assert account.quantities(4).tolist() == [350, 70]
    assert account.quantities(1).tolist() == [250, 70]
    assert account.changed_symbols == {"A", "B"}


def test_growing_pending_events_and_copy_isolation() -> None:
    account = Account(0, ("A",))
    for number in range(90):
        account.add_lot(Lot("A", number + 1, DAY, 90 - number, number))
    account.quantities(10)[:] = -1
    assert account.quantities(10).tolist() == [sum(range(81, 91))]
    account.apply_fill("A", -100, DAY, 1, 10, 0)
    assert account.quantities(0).tolist() == [0]
    assert account.quantities(90).tolist() == [sum(range(1, 91)) - 100]
    assert len(account.lots) == 89
    assert account.lots[80].quantity == 63


def test_custom_delay_bonus_and_backward_queries() -> None:
    account = Account(0, ("A", "B"))
    account.apply_fill("A", 100, DAY, 10, 0, 0)
    account.apply_fill("A", 200, DAY, 20, 0, 1)
    account.apply_fill("B", 300, DAY, 30, 0, 5)
    account.add_lot(Lot("A", 50, DAY + timedelta(days=2), 4, 0))
    for index, expected in [(5, [350, 300]), (0, [100, 0]), (4, [350, 0]), (1, [300, 0])]:
        assert account.quantities(index).tolist() == expected
    account.apply_fill("A", -150, DAY, 10, 1, 0)
    assert account.quantities(0).tolist() == [0, 0]
    assert account.quantities(1).tolist() == [150, 0]
    assert account.quantities(5).tolist() == [200, 300]


def test_oversell_preserves_partial_consumption_and_overflow_check() -> None:
    account = Account(0, ("A",))
    account.add_lot(Lot("A", 10, DAY, 0, 10))
    with pytest.raises(RuntimeError, match="more than settled"):
        account.apply_fill("A", -20, DAY, 10, 0, 0)
    assert account.lots == []
    account.add_lot(Lot("A", 1_000_000_001, DAY, 5, 10))
    assert account.quantities(0).tolist() == [0]
    with pytest.raises(OverflowError, match="supported bounds"):
        account.quantities()
    with pytest.raises(OverflowError, match="supported bounds"):
        account.quantities(5)


def test_random_operations_against_independent_fifo_records() -> None:
    generator = np.random.default_rng(9917)
    account = Account(0, ("A", "B", "C"))
    records: list[list[int]] = []
    for step in range(300):
        day = int(generator.integers(0, 15))
        column = int(generator.integers(0, 3))
        available = sum(row[1] for row in records if row[0] == column and row[2] <= day)
        if available and generator.random() < 0.55:
            quantity = int(generator.integers(1, available + 1))
            account.apply_fill(account.symbols[column], -quantity, DAY, 7, day, 0)
            _reference_sell(records, column, quantity, day)
        else:
            quantity = int(generator.integers(1, 100))
            delay = int(generator.integers(0, 7))
            account.apply_fill(account.symbols[column], quantity, DAY, step, day, delay)
            records.append([column, quantity, day + delay, step])
        _assert_reference(account, records, day)


def _reference_sell(records: list[list[int]], column: int, remaining: int, day: int) -> None:
    for row in records:
        if row[0] == column and row[2] <= day:
            consumed = min(remaining, row[1])
            row[1] -= consumed
            remaining -= consumed


def _assert_reference(account: Account, records: list[list[int]], day: int) -> None:
    assert account.quantities().tolist() == [
        sum(row[1] for row in records if row[0] == column) for column in range(3)
    ]
    assert account.quantities(day).tolist() == [
        sum(row[1] for row in records if row[0] == column and row[2] <= day) for column in range(3)
    ]
    assert [
        (lot.symbol, lot.quantity, lot.available_session, lot.price_units) for lot in account.lots
    ] == [(account.symbols[row[0]], row[1], row[2], row[3]) for row in records if row[1]]


def test_int64_overflow_does_not_wrap_or_append_lot() -> None:
    account = Account(0, ("A",))
    account.add_lot(Lot("A", 9_223_372_036_854_775_807, DAY, 5, 1))
    with pytest.raises(OverflowError, match="supported bounds"):
        account.add_lot(Lot("A", 1, DAY, 5, 1))
    assert len(account.lots) == 1
    assert account.lots[0].quantity == 9_223_372_036_854_775_807
    assert account.quantities(0).tolist() == [0]


def test_normal_quantity_queries_do_not_scan_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    account = Account(0, ("A", "B"))
    account.add_lot(Lot("A", 100, DAY, 1, 1))

    def unexpected_scan(*args: object, **kwargs: object) -> None:
        raise AssertionError("正常数量查询不应执行全量溢出扫描")

    with monkeypatch.context() as patch:
        patch.setattr(np, "any", unexpected_scan)
        assert account.quantities().tolist() == [100, 0]
        assert account.quantities(0).tolist() == [0, 0]
        assert account.quantities(1).tolist() == [100, 0]


def test_three_slot_ledger_keeps_compatibility_and_bound_checks() -> None:
    account = Account(0, ("A",))
    account._ledger_state = account._ledger_state[:3].copy()
    account.add_lot(Lot("A", 1_000_000_001, DAY, 1, 1))
    assert account.quantities(0).tolist() == [0]
    with pytest.raises(OverflowError, match="supported bounds"):
        account.quantities()
    account.apply_fill("A", -1, DAY, 1, 1, 0)
    assert account.quantities().tolist() == [1_000_000_000]
