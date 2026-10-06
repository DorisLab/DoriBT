from dataclasses import replace

import numpy as np
import pytest
from minute_fixtures import minute_data

from doribt import Backtest, BarExecution, FixedTicks, Instrument
from scripts.minute_case import FixedTargets, signals
from scripts.minute_reference import reference, verify


def test_independent_minute_reference_and_mutated_ledger_rejection(backend):
    data = minute_data(volume=100000, rule_changes={"price_tick": ".001"})
    data = replace(data, instruments=(Instrument(symbol="A", kind="etf"),))
    targets = np.full(480, 10000, dtype=np.int64)
    targets[250:] = 0
    test = Backtest(data, execution=BarExecution(participation=0.001, slippage=FixedTicks(1)))
    result = test.run(FixedTargets("A", targets), backend=backend)
    expected = reference(data, targets)
    verify(result, expected)
    broken = dict(expected, cash=list(expected["cash"]))
    broken["cash"][1] -= 100
    with pytest.raises(ValueError, match="cash mismatch"):
        verify(result, broken)
    with pytest.raises(ValueError, match="fills mismatch"):
        verify(result, dict(expected, fills=[]))


def test_minute_signal_prefix_is_independent_of_future_prices():
    data = minute_data()
    target = signals(data)
    bars = tuple(replace(bar, close=110000) if i >= 300 else bar for i, bar in enumerate(data.bars))
    changed = signals(replace(data, bars=bars))
    np.testing.assert_array_equal(target[:300], changed[:300])
    with pytest.raises(ValueError, match="windows"):
        signals(data, fast=300, slow=200)
