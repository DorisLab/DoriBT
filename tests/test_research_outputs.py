import hashlib
import json

import numpy as np
import pytest
from engine_fixtures import data_for
from minute_fixtures import minute_data

from doribt import Backtest, Metric, ResearchOutput, RunConfig, Series, Table


def test_recording_is_sparse_isolated_and_read_only_after_callback(backend):
    engine = Backtest(data_for([10, 11, 12]), config=RunConfig(backend=backend))
    captured = []

    def strategy(ctx):
        captured.append(ctx)
        if ctx.bar_index != 1:
            ctx.record(close=float(ctx.history("A")[-1]), count=ctx.bar_index)

    first = engine.run(strategy)
    assert first.outputs["strategy"].series["close"].values == (10.0, None, 12.0)
    with pytest.raises(RuntimeError, match="active"):
        captured[-1].record(close=42)
    with pytest.raises(TypeError):
        first.outputs["x"] = ResearchOutput()
    assert not engine.run(lambda ctx: None).outputs


def test_recording_works_on_minute_clocks_and_failed_strategy_expires_context():
    contexts = []

    def strategy(ctx):
        contexts.append(ctx)
        ctx.record(x=1)
        ctx.record(x=2)

    with pytest.raises(RuntimeError, match="duplicate record"):
        Backtest(minute_data(days=1, frequency="5min")).run(strategy)
    with pytest.raises(RuntimeError, match="active"):
        contexts[0].record(y=3)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "1"])
def test_nonfinite_or_nonnumeric_records_rejected(value):
    with pytest.raises(RuntimeError, match="research numeric"):
        Backtest(data_for([10])).run(lambda ctx: ctx.record(x=value))


def test_analyzer_snapshots_extensions_and_export_hashes(tmp_path):
    result = Backtest(data_for([10, 10, 11])).run(lambda ctx: ctx.target_positions({"A": 100}))
    rows = [{"symbol": "A", "score": 2.5}]
    scores = [None, 1.5, 2.5]
    output = ResearchOutput(
        metrics={"score": Metric(2.5, unit="ratio", description="自定义分数")},
        series={"signal": Series(sessions=result.sessions, values=scores)},
        tables={"ranks": Table(columns=["symbol", "score"], rows=rows)},
    )
    extended = result.analyze("factor", lambda r: output)
    rows[0]["score"] = 9
    scores[1] = 9
    assert result.outputs == {}
    assert extended.outputs["factor"].tables["ranks"].rows[0]["score"] == 2.5
    assert extended.outputs["factor"].series["signal"].values[1] == 1.5
    copied = extended.outputs["factor"].to_dict()
    copied["metrics"]["score"]["value"] = 100
    assert extended.outputs["factor"].metrics["score"].value == 2.5
    output_path = extended.export(tmp_path / "report", daily=True)
    saved = json.loads((output_path / "research.json").read_text(encoding="utf-8"))
    assert saved["outputs"]["factor"]["metrics"]["score"]["value"] == 2.5
    manifest = json.loads((output_path / "manifest.json").read_text())
    for name in ("research.json", "report.json"):
        assert (
            hashlib.sha256((output_path / name).read_bytes()).hexdigest()
            == manifest["files"][name]["sha256"]
        )
    with pytest.raises(ValueError, match="already exists"):
        extended.analyze("factor", lambda r: pytest.fail("must reject before executing"))


def test_invalid_extensions_fail_without_changing_existing_result():
    result = Backtest(data_for([10, 10, 11])).run(lambda ctx: None)
    with pytest.raises(ValueError, match="exactly match"):
        result.with_outputs(
            "bad", ResearchOutput(series={"x": Series(sessions=result.sessions[:1], values=[1])})
        )
    with pytest.raises(ValueError, match="unique"):
        ResearchOutput(metrics={"x": Metric(1)}, tables={"x": Table(columns=["a"], rows=[])})
    with pytest.raises(ValueError, match="columns"):
        Table(columns=["a"], rows=[{"b": 1}])
    with pytest.raises(ValueError):
        Table(columns=["a"], rows=[{"a": float("nan")}])
    with pytest.raises(ValueError):
        Metric(float("inf"))
    with pytest.raises(ValueError, match="ResearchOutput"):
        result.analyze("bad", lambda r: {"x": 1})
    assert not result.outputs


def test_numpy_research_values_are_normalized_for_json():
    result = Backtest(data_for([10, 11])).run(
        lambda ctx: ctx.record(mean=ctx.history("A").mean(), count=np.int64(ctx.bar_index))
    )
    saved = result.outputs["strategy"].to_dict()
    assert saved["series"]["mean"]["values"] == [10, 10.5]
    assert saved["series"]["count"]["values"] == [0, 1]
    assert json.loads(json.dumps(Metric(np.float64(1.5)).to_dict()))["value"] == 1.5


def test_failed_custom_output_write_never_publishes_partial_export(tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module("doribt.reporting.export")
    result = Backtest(data_for([10, 11])).run(lambda ctx: ctx.record(x=1))
    original = module._json

    def fail(path, value):
        if path.name == "research.json":
            raise OSError("custom output write failed")
        original(path, value)

    monkeypatch.setattr(module, "_json", fail)
    with pytest.raises(OSError, match="custom output write failed"):
        result.export(tmp_path / "failed", daily=True)
    assert list(tmp_path.iterdir()) == []
