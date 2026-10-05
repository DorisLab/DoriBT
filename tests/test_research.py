import builtins
from dataclasses import replace

import numpy as np
import pytest

from doribt.experimental import Backtest, CloseSignals, Costs, DailyBars
from doribt.experimental.api import accelerated


def data():
    return DailyBars(
        sessions=["2025-01-02", "2025-01-03", "2025-01-06"],
        open=[10, 10, 11],
        close=[10, 10.5, 11],
        upper_limit=[12, 12, 12],
        lower_limit=[8, 8, 8],
        suspended=[False, False, False],
    )


def test_close_decisions_execute_next_session_and_results_remember_capital(backend):
    bars = data()
    result = Backtest(bars, initial_cash=10000, costs=Costs(slippage_ticks=0)).run(
        CloseSignals(sessions=bars.sessions, hold=[True, False, True]),
        backend=backend,
    )
    np.testing.assert_array_equal(result.equity, [10000, 10445, 10890])
    np.testing.assert_array_equal(result.cash, [10000, 995, 10890])
    np.testing.assert_array_equal(result.position, [0, 900, 0])
    np.testing.assert_array_equal(
        result.fills["session"], np.array(bars.sessions, dtype="datetime64[D]")[1:]
    )
    assert result.total_return == pytest.approx(0.089)
    assert result.stats()["commission"] == 10
    assert result.stats()["fill_count"] == 2
    assert result.backend == backend


def test_final_close_is_not_executed_and_drawdown_includes_initial_cash():
    bars = data()
    empty = Backtest(bars).run(CloseSignals(sessions=bars.sessions, hold=[False, False, True]))
    assert empty.stats()["fill_count"] == 0 and empty.total_return == 0
    losing = replace(bars, open=[10, 10, 10], close=[10, 9, 9])
    result = Backtest(losing, initial_cash=10000, costs=Costs(slippage_ticks=0)).run(
        CloseSignals(sessions=bars.sessions, hold=[True, True, True]),
    )
    assert result.max_drawdown == pytest.approx(0.0905)


@pytest.mark.parametrize(
    "hold", [[1, 0, 1], [True], [[True], [False], [True]], [True, None, False]]
)
def test_ambiguous_or_misaligned_signals_fail(hold):
    bars = data()
    with pytest.raises(ValueError, match="boolean"):
        Backtest(bars).run(CloseSignals(sessions=bars.sessions, hold=hold))


@pytest.mark.parametrize(
    "sessions",
    [
        ["2025-01-03", "2025-01-06", "2025-01-07"],
        ["2025-01-02T12:00", "2025-01-03T12:00", "2025-01-06T12:00"],
        [1, 2, 3],
    ],
)
def test_signal_dates_are_not_silently_reindexed_or_truncated(sessions):
    with pytest.raises(ValueError):
        Backtest(data()).run(CloseSignals(sessions=sessions, hold=[True, False, False]))


def test_future_signals_do_not_change_past_fills_and_inputs_are_preserved():
    bars = data()
    hold = np.array([True, True, False])
    signals = CloseSignals(sessions=bars.sessions, hold=hold)
    first = Backtest(bars).run(signals)
    np.testing.assert_array_equal(hold, [True, True, False])
    hold[1:] = False
    second = Backtest(bars).run(signals)
    np.testing.assert_array_equal(first.equity[:2], second.equity[:2])
    np.testing.assert_array_equal(first.fills[:1], second.fills[:1])
    assert bars.open == [10, 10, 11]


def test_explicit_numba_without_extra_fails_without_fallback(monkeypatch):
    original = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == "numba":
            raise ImportError("not installed")
        return original(name, *args, **kwargs)

    accelerated.cache_clear()
    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", missing)
        with pytest.raises(ImportError, match="doribt\\[numba\\]"):
            Backtest(data()).run(
                CloseSignals(sessions=data().sessions, hold=[True] * 3), backend="numba"
            )
    accelerated.cache_clear()
