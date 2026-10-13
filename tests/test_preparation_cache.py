"""准备缓存保留真实规则断点、非活动区间及回调历史的时点边界。"""

from dataclasses import replace

import numpy as np
import pytest
from engine_fixtures import data_for
from minute_fixtures import minute_data

from doribt import Context, MarketData, RuleBook, RulePeriod, TradingRule
from doribt.accounting.account import Position
from doribt.kernels import compiled
from doribt.runtime.context import account_view
from doribt.runtime.intents import IntentBook


def rule_boundary_data():
    changes = {
        offset: dict(
            status="unlisted",
            open=None,
            high=None,
            low=None,
            close=None,
            volume=0,
            upper_limit=None,
            lower_limit=None,
        )
        for offset in range(0, 96, 2)
    }
    changes[1] = dict(status="suspended", volume=0)
    changes[98] = dict(volume=123456)
    base = minute_data(days=3, frequency="5min", symbols=("A", "B"), changes=changes)
    first = TradingRule(
        price_tick=".01",
        buy_minimum=100,
        buy_step=100,
        sell_step=100,
        settlement_days=1,
        stamp_duty_sell=".0005",
        transfer_fee=".00001",
    )
    second = replace(
        first,
        price_tick=".001",
        buy_minimum=200,
        buy_step=1,
        sell_step=1,
        sell_minimum=200,
        settlement_days=0,
        stamp_duty_sell=0,
        transfer_fee=0,
        allow_odd_lot_liquidation=False,
        order_maximum=100000,
    )
    periods = [
        RulePeriod(
            symbol=symbol,
            start=start,
            end=end,
            rule=rule,
            source="人工规则断点",
            version="1",
        )
        for symbol, start, end, rule in (
            ("A", base.sessions[1], base.sessions[1], first),
            ("A", base.sessions[2], base.sessions[2], second),
            ("B", base.sessions[0], base.sessions[2], first),
        )
    ]
    return replace(base, rules=RuleBook(tuple(periods)))


def test_minute_preparation_reuses_rules_without_skipping_day_boundaries(monkeypatch):
    data = rule_boundary_data()
    lookups, conversions = [], []
    original_at, original_compile = RuleBook.at, compiled._compile_rule

    def at(book, symbol, session):
        lookups.append((symbol, session))
        return original_at(book, symbol, session)

    def convert(rule):
        conversions.append(rule)
        return original_compile(rule)

    monkeypatch.setattr(RuleBook, "at", at)
    monkeypatch.setattr(compiled, "_compile_rule", convert)
    actual = compiled.compile_data(data)
    assert lookups == [
        ("B", data.sessions[0]),
        ("A", data.sessions[1]),
        ("B", data.sessions[1]),
        ("A", data.sessions[2]),
        ("B", data.sessions[2]),
    ]
    assert len(conversions) == 2
    for offset, bar in enumerate(data.bars):
        row, column = divmod(offset, 2)
        expected = [bar.open, int(bar.status), bar.upper_limit or 0, bar.lower_limit or 0]
        if column == 0 and row < 48:
            values, settlement = [0] * 10, 0
        elif column == 0 and row >= 96:
            values, settlement = [10, 200, 1, 1, 0, 0, bar.volume, 0, 200, 100000], 0
        else:
            values, settlement = [100, 100, 100, 100, 500, 10, bar.volume, 1, 1, 1000000000], 1
        assert actual.market[row, column].tolist() == expected + values
        assert actual.settlement[row, column] == settlement
        assert actual.closes[row, column] == bar.close


def test_preparation_still_rejects_active_rule_gaps():
    data = rule_boundary_data()
    incomplete = RuleBook(tuple(p for p in data.rules.periods if p.symbol == "B"))
    with pytest.raises(ValueError, match="missing historical rule for A on 2025-01-03"):
        replace(data, rules=incomplete)


def test_history_fields_are_lazy_cached_and_cannot_modify_shared_inputs(monkeypatch):
    data = data_for([10, 11, 12], [20, 21, 22])
    reads = []
    original = MarketData.prices

    def prices(data, field):
        reads.append(field)
        return original(data, field)

    monkeypatch.setattr(MarketData, "prices", prices)
    prepared = compiled.prepare(data)
    assert not reads
    assert tuple(prepared.history) == ("open", "high", "low", "close")
    assert len(prepared.history) == 4 and "close" in prepared.history
    with pytest.raises(KeyError, match="volume"):
        prepared.history["volume"]
    assert not reads
    closes = prepared.history["close"]
    assert prepared.history["close"] is closes and reads == ["close"]
    np.testing.assert_array_equal(closes, [[10, 20], [11, 21], [12, 22]])
    with pytest.raises(ValueError, match="WRITEABLE"):
        closes.setflags(write=True)
    with pytest.raises(ValueError, match="read-only"):
        closes[0, 0] = 99
    assert prepared.columns is prepared.columns
    assert tuple(prepared.columns) == data.symbols == ("A", "B")
    assert dict(prepared.columns) == {"A": 0, "B": 1}
    with pytest.raises(TypeError):
        prepared.columns["A"] = 1


def context_at(prepared, index, *, shared=True):
    data = prepared.data
    view = account_view(100000000, 100000000, [Position(s, 0, 0, 0) for s in data.symbols])
    options = {"columns": prepared.columns} if shared else {}
    return Context(data, index, prepared.history, view, (), IntentBook(), 100000000, **options)


@pytest.mark.parametrize("shared", [False, True])
def test_context_history_and_unknown_symbols_keep_original_contract(shared):
    data = data_for([10, 11, 12], [20, 21, 22])
    prepared = compiled.prepare(data)
    context = context_at(prepared, 1, shared=shared)
    assert context.symbols == data.symbols
    if shared:
        assert context._columns is prepared.columns
    np.testing.assert_array_equal(context.history("A"), [10, 11])
    np.testing.assert_array_equal(context.history("B", bars=1, field="open"), [21])
    later = context_at(prepared, 2, shared=shared)
    np.testing.assert_array_equal(later.history("B"), [20, 21, 22])
    np.testing.assert_array_equal(context.history("B"), [20, 21])
    with pytest.raises(ValueError, match="unknown strategy symbol: X"):
        context.history("X")
    with pytest.raises(ValueError, match="unknown strategy symbol: X"):
        context.order("X", 100)
    with pytest.raises(ValueError, match="unknown strategy symbol: X"):
        context.target_positions({"X": 100})
    with pytest.raises(ValueError, match="unknown strategy symbol: X"):
        context.target_weights({"X": ".1"})
    with pytest.raises(ValueError, match="history field"):
        context.history("A", field="volume")
