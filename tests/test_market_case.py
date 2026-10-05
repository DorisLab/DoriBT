"""The public validation harness must itself reject discrepancies and scope mistakes."""

import csv
import importlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from engine_fixtures import data_for

from doribt import Backtest, Costs, Instrument, MarketData, WeightTargets, china_rules

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("market_case")


def fixture_files(folder, *, gap=False):
    dates = ["2020-08-20", "2020-08-21", "2020-08-24", "2020-08-25", "2020-08-26"]
    prices = [10, 100, 100, 11, 10] if gap else [10, 10, 11, 12, 11]
    rows = [
        dict(
            session=session,
            symbol="ETF",
            status="trading",
            open=price,
            high=price,
            low=price,
            close=price,
            volume=100000,
            upper_limit="",
            lower_limit="",
        )
        for session, price in zip(dates, prices, strict=True)
    ]
    if gap:
        rows[2].update(status="suspended", volume=0)
    market, calendar = folder / "market.csv", folder / "calendar.csv"
    with market.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    calendar.write_text("session\n" + "\n".join(dates), encoding="utf-8")
    return market, calendar


def test_real_case_harness_can_be_exercised_with_public_artificial_rows(tmp_path, harness, backend):
    market, calendar = fixture_files(tmp_path, gap=True)
    data, rows = harness.load_market(market, calendar, "szse_equity_etf", "artificial test")
    report = harness.validate(data, rows, fast=1, slow=2, backend=backend)
    assert set(report) == {"buy_and_hold", "moving_average"}
    assert report["buy_and_hold"]["reference"] == "exact Decimal equality"
    # At 100.001 buy 900 shares + 27 commission, leaving 9,972.10.
    # The next open is suspended; at 11.001 another 900 + 5 leaves 66.20.
    # A final 10.001 open cannot buy a 100-share lot. The original 9,500 target persists.
    assert report["buy_and_hold"]["stats"]["partial_order_count"] == 2
    assert report["buy_and_hold"]["stats"]["unfilled_order_count"] == 2
    assert report["buy_and_hold"]["stats"]["final_equity"] == 18066.2


def test_validator_detects_injected_accounting_error(tmp_path, harness, monkeypatch):
    market, calendar = fixture_files(tmp_path)
    data, rows = harness.load_market(market, calendar, "szse_equity_etf", "test")
    real_run = Backtest.run

    def corrupt(self, *args, **kwargs):
        result = real_run(self, *args, **kwargs)
        return replace(result, cash_units=result.cash_units + 100)

    monkeypatch.setattr(Backtest, "run", corrupt)
    with pytest.raises(AssertionError, match="differs: cash"):
        harness.validate(data, rows, fast=1, slow=2, backend="python")


def test_optimized_python_cannot_remove_validator_checks():
    checked = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            "from market_case import require_equal; require_equal(1,2,'test')",
        ],
        cwd=SCRIPTS,
        capture_output=True,
        text=True,
    )
    assert checked.returncode != 0
    assert "independent validation differs: test" in checked.stderr


def test_scope_and_missing_independent_calendar_rows_are_rejected(tmp_path, harness):
    market, calendar = fixture_files(tmp_path)
    with pytest.raises(ValueError, match="equity ETF profile"):
        harness.load_market(market, calendar, "sse_main", "test")
    with pytest.raises(ValueError, match="one ETF"):
        harness.check_scope(data_for([10, 10]))
    calendar.write_text(calendar.read_text() + "\n2020-08-27", encoding="utf-8")
    with pytest.raises(ValueError, match="missing 1 market rows"):
        harness.load_market(market, calendar, "sse_equity_etf", "test")


def test_report_publication_never_overwrites_and_invalid_json_leaves_no_output(tmp_path, harness):
    destination = tmp_path / "report.json"
    harness.write_report(destination, {"verified": True})
    assert json.loads(destination.read_text()) == {"verified": True}
    with pytest.raises(FileExistsError):
        harness.write_report(destination, {"verified": False})
    assert json.loads(destination.read_text()) == {"verified": True}
    with pytest.raises(ValueError):
        harness.write_report(tmp_path / "bad.json", {"invalid": float("nan")})
    assert list(tmp_path.iterdir()) == [destination]


def test_159915_daily_boundary_transition_uses_supplied_historical_limits(backend):
    # Regression for the official 2020-08-24 ETF list, with artificial prices.
    dates = ["2020-08-20", "2020-08-21", "2020-08-24"]
    rows = [
        dict(
            session=day,
            symbol="159915.SZ",
            status="trading",
            open=opening,
            high=opening,
            low=close,
            close=close,
            volume=100000,
            upper_limit=upper,
            lower_limit=lower,
        )
        for day, opening, close, upper, lower in zip(
            dates, [100, 110, 110], [100, 100, 110], [110, 110, 120], [90, 90, 80], strict=True
        )
    ]
    data = MarketData.from_records(
        rows,
        calendar=dates,
        instruments=[Instrument(symbol="159915.SZ", kind="etf")],
        rules=china_rules({"159915.SZ": "szse_equity_etf"}, start=dates[0], end=dates[-1]),
        source="artificial prices; verified 10% to 20% rule transition",
    )
    result = Backtest(data, costs=Costs(commission=0, minimum_commission=0)).run(
        WeightTargets(sessions=data.sessions, weights={"159915.SZ": [0.1] * 3}), backend=backend
    )
    assert [(str(order.session), order.reason.value, order.filled) for order in result.orders] == [
        ("2020-08-21", "buy_at_upper_limit", 0),
        ("2020-08-24", "none", 100),
    ]
