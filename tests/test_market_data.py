import csv
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime

import numpy as np
import pytest
from market_fixtures import INSTRUMENTS, SESSIONS, inactive, market, records, rules

from doribt import Instrument, MarketData, TradingStatus
from doribt.bars import Bar
from doribt.validation import day, integer


def test_canonical_rows_and_read_only_named_prices(tmp_path):
    rows = records()
    data = market(reversed(rows))
    assert data.symbols == ("A", "B")
    assert data.sessions == tuple(map(date.fromisoformat, SESSIONS))
    assert data.bars[0].open == 100_000
    assert data.fingerprint == market().fingerprint
    np.testing.assert_array_equal(data.prices("close"), [[10.5, 10.5]] * 3)
    with pytest.raises(ValueError, match="read-only"):
        data.prices("close")[0, 0] = 99
    with pytest.raises(FrozenInstanceError):
        data.source = "altered"
    path = tmp_path / "bars.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    loaded = MarketData.from_csv(
        path, calendar=SESSIONS, instruments=INSTRUMENTS, rules=rules(), source="fixture"
    )
    assert loaded.fingerprint == data.fingerprint
    assert market(source="other snapshot").fingerprint != data.fingerprint


@pytest.mark.parametrize(
    "edit,match",
    [
        (lambda r: r[:-1], "missing 1 market rows"),
        (lambda r: r + [r[0]], "duplicate bar"),
        (lambda r: [r[0] | {"session": "2025-01-04"}, *r[1:]], "unexpected"),
        (lambda r: [r[0] | {"symbol": "unknown"}, *r[1:]], "unexpected"),
    ],
)
def test_missing_duplicate_and_unexpected_rows(edit, match):
    with pytest.raises(ValueError, match=match):
        market(edit(records()))


@pytest.mark.parametrize(
    "change,match",
    [
        ({"status": "unknown"}, "unknown trading status"),
        ({"status": 0}, "status must be"),
        ({"open": None}, "require explicit OHLC"),
        ({"open": "nan"}, "non-finite"),
        ({"open": "10.001"}, "off tick"),
        ({"open": "10.00001"}, "unsupported precision"),
        ({"high": "9.99"}, "invalid OHLC range"),
        ({"upper_limit": "10.90"}, "outside declared daily limits"),
        ({"upper_limit": None}, "both be supplied"),
        ({"volume": -1}, "outside supported bounds"),
        ({"volume": 1.5}, "unsupported precision"),
        ({"status": "suspended"}, "zero volume"),
        ({"status": "delisted"}, "empty prices"),
    ],
)
def test_invalid_market_facts_fail_before_execution(change, match):
    rows = records()
    rows[0].update(change)
    with pytest.raises(ValueError, match=match):
        market(rows)


def test_missing_columns_do_not_imply_default_trading():
    rows = records()
    del rows[0]["upper_limit"]
    with pytest.raises(ValueError, match="missing bar columns: upper_limit"):
        market(rows)


def test_inactive_rows_explicit_unlimited_days_and_suspension():
    rows = records()
    rows[0] = inactive(rows[0], "unlisted")
    rows[2].update(upper_limit=None, lower_limit=None)
    rows[4].update(status="suspended", volume=0)
    data = market(rows)
    assert np.isnan(data.prices("close")[0, 0])
    assert data.bars[2].upper_limit is None
    assert data.bars[4].status == TradingStatus.SUSPENDED


@pytest.mark.parametrize(
    "state,match",
    [
        ("delisted", "reappears after delisting"),
        ("unlisted", "becomes unlisted"),
    ],
)
def test_lifecycle_cannot_run_backward(state, match):
    rows = records()
    rows[2] = inactive(rows[2], state)
    with pytest.raises(ValueError, match=match):
        market(rows)


@pytest.mark.parametrize("calendar", [[], SESSIONS[::-1], [SESSIONS[0]] * 3])
def test_calendar_is_explicit_strict_and_nonempty(calendar):
    with pytest.raises(ValueError, match="calendar must be"):
        market(calendar=calendar)


@pytest.mark.parametrize(
    "value", ["20250102", "2025-1-02", "2025-02-30", 20250102, datetime(2025, 1, 2)]
)
def test_session_rejects_ambiguous_dates(value):
    with pytest.raises(ValueError, match="session"):
        day(value)


def test_direct_construction_cannot_bypass_unit_checks():
    data = market()
    with pytest.raises(ValueError, match="unsupported precision"):
        replace(data.bars[0], open=0.5)
    with pytest.raises(ValueError, match="TradingStatus"):
        replace(data.bars[0], status=0)
    with pytest.raises(ValueError, match="empty prices"):
        replace(data.bars[0], status=TradingStatus.DELISTED)
    bar = Bar(date(2025, 1, 2), "A", TradingStatus.UNLISTED, 0, 0, 0, 0, 0, None, None)
    with pytest.raises(ValueError, match="inactive rows"):
        replace(bar, upper_limit=120_000, lower_limit=80_000)


@pytest.mark.parametrize("value", [True, "inf", object(), None, 10**20, 0.1])
def test_exact_integer_conversion_rejects_unsafe_values(value):
    with pytest.raises(ValueError):
        integer(value, 1, "test", 0, 100)


def test_precision_is_not_rounded_by_decimal_context():
    with pytest.raises(ValueError, match="unsupported precision"):
        integer("1.000000000000000000000000000001", 10_000, "price", 0, 100_000)
    assert integer("1.000000000000000000000000000000", 10_000, "price", 0, 100_000) == 10_000


def test_identity_and_source_are_required():
    with pytest.raises(ValueError, match="unique"):
        market(instruments=INSTRUMENTS * 2)
    with pytest.raises(ValueError, match="source"):
        market(source=" ")
    with pytest.raises(ValueError, match="symbol"):
        Instrument(symbol=" A ", kind="stock")
    with pytest.raises(ValueError, match="stock or etf"):
        Instrument(symbol="A", kind="future")
    with pytest.raises(ValueError, match="price field"):
        market().prices("adjusted_close")
