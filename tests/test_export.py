"""从导出文件重建账户；导出失败时保留已有结果。"""

import csv
import hashlib
import importlib
import json
from dataclasses import replace

import numpy as np
import pytest
from corporate_fixtures import distribution, market_with_actions
from engine_fixtures import data_for
from minute_fixtures import minute_data

from doribt import Backtest, Benchmark, Costs, WeightTargets


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def simple():
    return Backtest(data_for([10, 10, 11])).run(lambda ctx: ctx.target_positions({"A": 100}))


def test_export_reconstructs_cash_positions_receivables_and_tax_from_disk(tmp_path, backend):
    data = market_with_actions([10, 10, 9, 9, 9], [distribution()])
    result = Backtest(
        data, initial_cash=10000, costs=Costs(commission=0, minimum_commission=0)
    ).run(WeightTargets(sessions=data.sessions, weights={"A": [1, 0, 0, 0, 0]}), backend=backend)
    output = result.export(tmp_path / "研究结果", periods_per_year=252)
    account = read_csv(output / "account.csv")
    positions = read_csv(output / "positions.csv")
    ledger = read_json(output / "ledger.json")
    assert [int(row["cash_units"]) for row in account] == [
        100000000,
        0,
        90000000,
        88000000,
        98000000,
    ]
    assert [int(row["equity_units"]) for row in account] == [
        100000000,
        100000000,
        98000000,
        98000000,
        98000000,
    ]
    assert ledger["taxes"][0]["amount_units"] == 2000000
    assert ledger["taxes"][0]["paid_units"] == 2000000
    assert ledger["entitlements"][0]["cash_paid"] is True
    assert ledger["fills"][0]["session"] == "2025-01-03"
    assert ledger["fills"][0]["quantity"] == 1000
    for row in account:
        assets = sum(int(p["value_units"]) for p in positions if p["session"] == row["session"])
        expected = int(row["cash_units"]) + assets + int(row["dividend_receivable_units"])
        expected -= int(row["tax_payable_units"])
        assert expected == int(row["equity_units"])
    # The consumer uses only exported facts to reconstruct cash, not engine helper functions.
    cash = 100000000
    for row in account:
        for fill in ledger["fills"]:
            if fill["session"] == row["session"]:
                cash -= fill["quantity"] * fill["price_units"]
                cash -= (
                    fill["commission_units"] + fill["stamp_duty_units"] + fill["transfer_fee_units"]
                )
        for event in ledger["corporate_events"]:
            if event["session"] == row["session"] and event["kind"] == "cash_paid":
                cash += event["amount_units"]
        for payment in ledger["tax_payments"]:
            if payment["session"] == row["session"]:
                cash -= payment["amount_units"]
        assert cash == int(row["cash_units"])
    manifest = read_json(output / "manifest.json")
    assert manifest["data_fingerprint"] == data.fingerprint
    assert manifest["run_fingerprint"] == result.run_info.fingerprint
    for name, entry in manifest["files"].items():
        content = (output / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]
        assert len(content) == entry["bytes"]
    assert read_json(output / "stats.json")["total_return"] == pytest.approx(-0.02)
    assert (
        read_json(output / "run.json")["data"]["actions"][0]["source"] == "fictional announcement"
    )


def test_empty_tables_keep_schema_and_undefined_metrics_are_json_null(tmp_path):
    result = Backtest(data_for([10] * 3)).run(lambda ctx: None)
    result = replace(result, equity_units=np.array([1000000000, 0, 0]))
    output = result.export(tmp_path / "empty", periods_per_year=252)
    assert read_csv(output / "fills.csv") == []
    assert "price_units" in (output / "fills.csv").read_text()
    assert read_json(output / "ledger.json")["orders"] == []
    assert read_json(output / "stats.json")["sharpe"] is None
    assert read_csv(output / "account.csv")[-1]["return"] == ""
    assert "NaN" not in (output / "stats.json").read_text()


@pytest.mark.parametrize("kind", ["file", "empty_directory", "earlier_export"])
def test_existing_destination_is_never_replaced(tmp_path, kind):
    target = tmp_path / "existing"
    if kind == "file":
        target.write_bytes(b"original")
    elif kind == "empty_directory":
        target.mkdir()
    else:
        simple().export(target)
    previous = {str(p): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError):
        simple().export(target)
    if kind == "file":
        assert target.read_bytes() == b"original"
    else:
        assert previous == {str(p): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    assert list(tmp_path.iterdir()) == [target]


def test_failed_write_cleans_staging_and_preserves_other_exports(tmp_path, monkeypatch):
    previous = simple().export(tmp_path / "success")
    original = (previous / "manifest.json").read_bytes()
    module = importlib.import_module("doribt.reporting.export")

    def fail(result, folder):
        (folder / "partial").write_text("incomplete")
        raise OSError("simulated disk failure")

    monkeypatch.setattr(module, "_ledger", fail)
    with pytest.raises(OSError, match="simulated disk failure"):
        simple().export(tmp_path / "failed")
    assert (previous / "manifest.json").read_bytes() == original
    assert list(tmp_path.iterdir()) == [previous]


@pytest.mark.parametrize("kind", ["file", "empty_directory", "nonempty_directory"])
def test_competing_destination_created_just_before_publish_is_preserved(
    tmp_path, monkeypatch, kind
):
    module = importlib.import_module("doribt.reporting.export")
    real_publish = module.publish

    def competitor(source, destination):
        if kind == "file":
            destination.write_bytes(b"winner")
        else:
            destination.mkdir()
            if kind == "nonempty_directory":
                (destination / "winner").write_bytes(b"winner")
        real_publish(source, destination)

    monkeypatch.setattr(module, "publish", competitor)
    with pytest.raises(FileExistsError):
        simple().export(tmp_path / "race")
    target = tmp_path / "race"
    if kind == "file":
        assert target.read_bytes() == b"winner"
    elif kind == "nonempty_directory":
        assert (target / "winner").read_bytes() == b"winner"
    else:
        assert list(target.iterdir()) == []
    assert list(tmp_path.iterdir()) == [target]


def test_corruption_after_manifest_is_rejected_before_publication(tmp_path, monkeypatch):
    module = importlib.import_module("doribt.reporting.export")
    real_manifest = module._manifest

    def corrupt(result, folder):
        real_manifest(result, folder)
        (folder / "account.csv").write_bytes(b"corrupted")

    monkeypatch.setattr(module, "_manifest", corrupt)
    with pytest.raises(OSError, match="verification failed"):
        simple().export(tmp_path / "bad")
    assert list(tmp_path.iterdir()) == []


def test_invalid_benchmark_has_no_filesystem_side_effects(tmp_path):
    benchmark = Benchmark(sessions=["2025-01-01"], prices=[1], name="x", source="x")
    with pytest.raises(ValueError, match="exactly match"):
        simple().export(tmp_path / "invalid", benchmark=benchmark)
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(FileNotFoundError):
        simple().export(tmp_path / "missing" / "parent")


def test_optional_plot_and_benchmark_export_contains_rendered_series(tmp_path):
    result = simple()
    benchmark = Benchmark(
        sessions=result.sessions, prices=[1, 1, 1.1], name="Reference", source="fixture"
    )
    figure = result.plot(benchmark=benchmark)
    assert len(figure.axes) == 3
    np.testing.assert_allclose(figure.axes[0].lines[0].get_ydata(), result.nav)
    np.testing.assert_allclose(figure.axes[0].lines[1].get_ydata(), [1, 1, 1.1])
    np.testing.assert_allclose(figure.axes[1].lines[0].get_ydata(), result.nav - benchmark.nav)
    np.testing.assert_allclose(figure.axes[-1].lines[0].get_ydata(), -result.drawdown)
    output = result.export(tmp_path / "plotted", benchmark=benchmark, plot=True)
    assert (output / "equity.png").read_bytes().startswith(b"\x89PNG")
    assert (output / "equity.png").stat().st_size > 10000
    assert read_json(output / "benchmark.json")["source"] == "fixture"
    assert read_json(output / "stats.json")["benchmark_total_return"] == pytest.approx(0.1)
    assert "equity.png" in read_json(output / "manifest.json")["files"]


@pytest.mark.parametrize("frequency,minutes", [("1min", 1), ("5min", 5)])
def test_minute_plot_preserves_bar_times_and_market_timezone(tmp_path, frequency, minutes):
    from matplotlib import rc_context
    from matplotlib.dates import date2num

    result = Backtest(minute_data(days=1, frequency=frequency)).run(lambda ctx: None)
    benchmark = Benchmark(
        sessions=result.sessions,
        prices=[10] * len(result.sessions),
        name="Reference",
        source="synthetic minute fixture",
    )
    with rc_context(
        {
            "timezone": "UTC",
            "date.autoformatter.hour": "%Y-%m-%d %H:%M",
            "date.autoformatter.minute": "%Y-%m-%d %H:%M",
        }
    ):
        figure = result.plot(benchmark=benchmark)
        curves = [*figure.axes[0].lines, *(axis.lines[0] for axis in figure.axes[1:])]
        for line in curves:
            assert tuple(line.get_xdata()) == result.sessions
            x = line.get_xdata(orig=False)
            assert x[1] - x[0] == pytest.approx(minutes / (24 * 60))
        output = result.export(tmp_path / "minute-plot", benchmark=benchmark, plot=True)
        formatter = figure.axes[-1].xaxis.get_major_formatter()
        figure.axes[-1].xaxis.get_majorticklocs()
        first = result.sessions[0]
        assert formatter.format_data(date2num(first)) == first.strftime("%Y-%m-%d %H:%M")
    assert (output / "equity.png").read_bytes().startswith(b"\x89PNG")


def test_plot_without_chinese_fonts_uses_readable_fallback(tmp_path, monkeypatch):
    from matplotlib.font_manager import fontManager

    monkeypatch.setattr(fontManager, "get_font_names", lambda: [])
    figure = simple().plot()
    assert len(figure.axes) == 2
    assert figure.axes[0].get_title() == "DoriBT | Backtest performance"
    figure.savefig(tmp_path / "fallback.png")
    assert (tmp_path / "fallback.png").read_bytes().startswith(b"\x89PNG")
