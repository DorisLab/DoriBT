"""具名账本协议的扩容、交收堆与 FIFO 用独立预期复核。"""

from datetime import date

import numpy as np
import pytest
from minute_fixtures import minute_data

from doribt import Backtest, BarExecution, Costs, PositionTargets
from doribt.accounting.account import Account, Lot
from doribt.kernels.account_ledger import (
    AVAILABLE,
    COLUMN,
    EVENT_COUNT,
    LOT_COUNT,
    OVERFLOW_SEEN,
    QUANTITY,
    ledger_advance,
    ledger_fill,
    register_ledger,
)
from doribt.kernels.buffers import grow_table, grow_vector
from doribt.kernels.ledger_state import LedgerState, allocate_ledger, grow_ledger

DAY = date(2025, 1, 2)


def exercise_state(state):
    ledger_advance(0, state.lots, state.heap, state.control, state.settled)
    for index in range(20):
        state = grow_ledger(state, 1)
        ledger_fill(
            100,
            index % 2,
            739253,
            5 if index % 2 == 0 else 0,
            index + 1,
            state.lots,
            state.heads,
            state.tails,
            state.heap,
            state.control,
            state.totals,
            state.settled,
        )
    ledger_advance(5, state.lots, state.heap, state.control, state.settled)
    ledger_fill(
        -450,
        0,
        0,
        0,
        0,
        state.lots,
        state.heads,
        state.tails,
        state.heap,
        state.control,
        state.totals,
        state.settled,
    )
    ledger_advance(0, state.lots, state.heap, state.control, state.settled)
    return state


def test_protocol_keeps_fifo_and_rebuilds_pending_heap_after_growth(backend):
    operation = exercise_state
    if backend == "numba":
        from numba import njit
        from numba.extending import register_jitable

        register_ledger()
        for function in (grow_table, allocate_ledger, grow_ledger):
            register_jitable(function)
        operation = njit(cache=True)(exercise_state)
    state = operation(allocate_ledger(2, 2))
    assert isinstance(state, LedgerState)
    assert len(state.lots) >= 20
    assert state.control.tolist() == [20, 6, 0, 0]
    assert state.totals.tolist() == [550, 1000]
    assert state.settled.tolist() == [0, 1000]
    assert state.heads.tolist() == [8, 1]
    assert state.tails.tolist() == [18, 19]
    assert sorted(state.heap[: state.control[EVENT_COUNT]].tolist()) == [8, 10, 12, 14, 16, 18]
    assert state.lots[:8:2, QUANTITY].tolist() == [0, 0, 0, 0]
    assert state.lots[8, QUANTITY] == 50
    assert state.lots[8, AVAILABLE] == 5
    ledger_advance(5, state.lots, state.heap, state.control, state.settled)
    assert state.settled.tolist() == [550, 1000]
    assert state.control[EVENT_COUNT] == 0


def test_account_owns_current_buffers_and_growth_preserves_live_indexes():
    account = Account(0, ("A", "B"))
    account.add_lot(Lot("A", 1_000_000_001, DAY, 3, 10))
    original = account.numeric_state()
    assert original.control[OVERFLOW_SEEN] == 1
    account.reserve_lots(1)
    assert account.numeric_state() is original
    account.reserve_lots(40)
    expanded = account.numeric_state()
    assert expanded is not original
    assert len(expanded.lots) >= 41
    assert expanded.lots is not original.lots and expanded.heap is not original.heap
    for name in ("heads", "tails", "control", "totals", "settled"):
        assert getattr(expanded, name) is getattr(original, name)
    assert expanded.control.tolist() == [1, 1, -1, 1]
    assert expanded.heap[0] == 0
    assert expanded.lots[0, COLUMN] == 0
    assert expanded.lots[0, QUANTITY] == 1_000_000_001
    assert account.quantities(2).tolist() == [0, 0]
    with pytest.raises(OverflowError, match="supported bounds"):
        account.quantities(3)
    account.apply_fill("A", -1, DAY, 10, 3, 0)
    assert account.quantities().tolist() == [1_000_000_000, 0]
    assert expanded.control[LOT_COUNT] == 1


def test_generic_table_growth_copies_only_used_rows_and_keeps_numbers():
    rows = np.array([[11, 12], [99, 98]], dtype=np.int64)
    assert grow_table(rows, 1, 1) is rows
    expanded = grow_table(rows, 1, 3)
    assert expanded.tolist() == [[11, 12], [0, 0], [0, 0], [0, 0]]
    rows[0] = -1
    assert expanded[0].tolist() == [11, 12]


def test_generic_vector_growth_copies_only_used_ids():
    values = np.array([11, 99], dtype=np.int64)
    assert grow_vector(values, 1, 1) is values
    expanded = grow_vector(values, 1, 3)
    assert expanded.tolist() == [11, 0, 0, 0]
    values[0] = -1
    assert expanded[0] == 11


def test_full_backtest_trade_stream_matches_independent_account_after_lot_growth(backend):
    data = minute_data(days=1, frequency="5min", settlement=0, volume=100000)
    values = tuple(100 if index % 2 == 0 else 200 for index in range(len(data.timeline)))
    target = PositionTargets(sessions=data.timeline, quantities={"A": values})
    engine = Backtest(
        data,
        costs=Costs(commission=0, minimum_commission=0),
        execution=BarExecution(participation=1),
    )
    scheduled = engine.run(target, backend=backend)

    def callback(ctx):
        ctx.target_positions({"A": values[ctx.bar_index]})

    observed = engine.run(callback, backend=backend)
    expected = np.array([0, *values[:-1]])
    assert scheduled.holdings[:, 0].tolist() == expected.tolist()
    assert scheduled.sellable[:, 0].tolist() == expected.tolist()
    assert scheduled.cash_units.tolist() == (1_000_000_000 - expected * 100000).tolist()
    assert scheduled.equity_units.tolist() == [1_000_000_000] * len(data.timeline)
    assert len(scheduled.fills) == len(data.timeline) - 1
    for name in (
        "equity_units",
        "cash_units",
        "holdings",
        "sellable",
        "frozen_cash_units",
        "frozen_shares",
    ):
        np.testing.assert_array_equal(getattr(scheduled, name), getattr(observed, name))
    for name in ("orders", "fills", "intents", "tax_lots"):
        assert getattr(scheduled, name) == getattr(observed, name)
