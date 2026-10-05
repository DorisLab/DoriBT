"""Performance evidence is emitted only after full workload result agreement."""

import copy
import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_memory_sampling_includes_windows_redirector_child(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    harness = importlib.import_module("benchmark")
    child = SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=1000))
    observer = SimpleNamespace(
        memory_info=lambda: SimpleNamespace(rss=100), children=lambda recursive: [child]
    )
    monkeypatch.setattr(harness.psutil, "Process", lambda pid: observer)
    statuses = iter([None, 0])
    process = SimpleNamespace(pid=1, poll=lambda: next(statuses))
    assert harness.sample(process, 5) == 1100


def test_performance_report_rejects_wrong_parameter_account(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    workloads = importlib.import_module("benchmark_workloads")
    data = workloads.synthetic_market(60, 2)
    single = workloads.single_case(data, "python", 1, 2)
    portfolio = workloads.portfolio_case(data, "python", 1)
    reports = [{"single": single, "portfolio": portfolio}] * 2
    workloads.verify_backends(reports)
    corrupted = copy.deepcopy(reports[0])
    corrupted["single"]["parameters"]["cases"][1]["result_sha256"] = "bad ledger"
    with pytest.raises(AssertionError, match="digests differ"):
        workloads.verify_backends([reports[0], corrupted])


@pytest.mark.numba
def test_benchmark_fresh_processes_emit_checked_metrics_without_raw_market_data(tmp_path):
    output = tmp_path / "benchmark.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/benchmark.py"),
            "--output",
            str(output),
            "--days",
            "60",
            "--assets",
            "2",
            "--repeats",
            "1",
            "--parameters",
            "2",
        ],
        check=True,
        cwd=ROOT,
        timeout=120,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema"] == "doribt.performance/1"
    assert len(report["verified_result_sha256"]) == 64
    assert [item["backend"] for item in report["reports"]] == ["python", "numba"]
    for item in report["reports"]:
        assert item["sampled_peak_rss_bytes"] > 0
        assert item["new_numba_cache"] is True
        assert item["single"]["parameters"]["count"] == 2
        assert item["portfolio"]["assets"] == 2
        assert item["single"]["first_run_seconds"] > 0
        assert "bars" not in item["single"]
