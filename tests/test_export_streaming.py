"""流式导出保持原字节、空表结构及失败时的完整发布边界。"""

import csv
import hashlib
import importlib
import json
import os
from dataclasses import asdict

import numpy as np
import pytest
from engine_fixtures import data_for

from doribt import Backtest, Costs, RunConfig
from doribt.serialization import encode

MODULE = importlib.import_module("doribt.reporting.export")


def result(*, config=None, backend="python"):
    return Backtest(
        data_for([10, 10, 11]),
        **({"config": config} if config else {"costs": Costs(commission=0, minimum_commission=0)}),
    ).run(
        lambda ctx: ctx.target_positions({"A": 100}) if ctx.bar_index == 0 else None,
        backend=backend,
    )


@pytest.mark.parametrize("bar_execution", [False, True])
def test_zero_reservations_are_read_only_and_keep_account_facts(backend, bar_execution):
    config = RunConfig(costs=Costs(commission=0, minimum_commission=0)) if bar_execution else None
    output = result(config=config, backend=backend)
    before = output.run_info.fingerprint
    assert np.all(output.frozen_cash_units == 0)
    assert np.all(output.frozen_shares == 0)
    with pytest.raises(ValueError, match="read-only"):
        output.frozen_cash_units[0] = 10000
    with pytest.raises(ValueError, match="read-only"):
        output.frozen_shares[0, 0] = 123
    assert output.run_info.fingerprint == before
    assert output.holdings[-1, 0] == 100


def test_account_csv_has_independent_expected_rows_and_positions(tmp_path):
    MODULE._account(result(), tmp_path)
    account = (tmp_path / "account.csv").read_bytes()
    assert account == (
        b"session,cash_units,equity_units,available_cash_units,frozen_cash_units,"
        b"dividend_receivable_units,tax_payable_units,nav,return,drawdown\r\n"
        b"2025-01-02,1000000000,1000000000,1000000000,0,0,0,1.0,0.0,0.0\r\n"
        b"2025-01-03,990000000,1000000000,990000000,0,0,0,1.0,0.0,0.0\r\n"
        b"2025-01-06,990000000,1001000000,990000000,0,0,0,1.001,"
        b"0.0009999999999998899,0.0\r\n"
    )
    assert (tmp_path / "positions.csv").read_bytes() == (
        b"session,symbol,quantity,sellable,frozen_quantity,pending_quantity,close_units,"
        b"value_units\r\n2025-01-02,A,0,0,0,0,100000,0\r\n"
        b"2025-01-03,A,100,0,0,0,100000,10000000\r\n"
        b"2025-01-06,A,100,100,0,0,110000,11000000\r\n"
    )


def test_streamed_ledger_bytes_equal_previous_canonical_format(tmp_path):
    output = result()
    MODULE._ledger(output, tmp_path)
    names = (
        "orders",
        "fills",
        "intents",
        "entitlements",
        "corporate_events",
        "taxes",
        "tax_lots",
        "tax_payments",
    )
    expected = {name: [asdict(item) for item in getattr(output, name)] for name in names}
    assert (tmp_path / "ledger.json").read_bytes() == (encode(expected) + "\n").replace(
        "\n", "\r\n" if os.name == "nt" else "\n"
    ).encode()
    for name in names:
        with (tmp_path / f"{name}.csv").open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames
            rows = list(reader)
        assert len(rows) == len(expected[name])
    assert json.loads((tmp_path / "ledger.json").read_text())["fills"][0]["quantity"] == 100


def test_csv_consumes_single_pass_rows_and_preserves_nested_cells(tmp_path):
    expected = 'id,cell\r\n1,"[null, {""值"": 2}]"\r\n'
    rows = iter([{"id": 1, "cell": [None, {"值": 2}]}])
    MODULE._csv(tmp_path / "once.csv", ("id", "cell"), rows)
    assert (tmp_path / "once.csv").read_bytes() == expected.encode()
    MODULE._csv(tmp_path / "empty.csv", ("id", "cell"), iter(()))
    assert (tmp_path / "empty.csv").read_bytes() == b"id,cell\r\n"


def test_manifest_hashes_large_files_without_full_read(tmp_path, monkeypatch):
    payload = b"synthetic\x00" * 200000
    path = tmp_path / "large.csv"
    path.write_bytes(payload)
    monkeypatch.setattr(type(path), "read_bytes", lambda path: pytest.fail("requires chunked hash"))
    assert MODULE._file_info(path) == {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }


def test_generator_failure_preserves_previous_export_and_cleans_staging(tmp_path, monkeypatch):
    output = result()
    previous = output.export(tmp_path / "success")
    original = (previous / "manifest.json").read_bytes()

    def broken_rows(result):
        yield {"session": "partial"}
        raise OSError("simulated generator failure")

    monkeypatch.setattr(MODULE, "_position_rows", broken_rows)
    with pytest.raises(OSError, match="generator failure"):
        output.export(tmp_path / "failed")
    assert (previous / "manifest.json").read_bytes() == original
    assert list(tmp_path.iterdir()) == [previous]
