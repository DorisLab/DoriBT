"""Standard tables and canonical metadata, staged before a no-replace publish."""

import csv
import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any

from doribt.accounting.orders import Fill, IntentRecord, Order
from doribt.accounting.rights import CorporateEvent, EntitlementRecord
from doribt.accounting.taxes import TaxLotRecord, TaxPayment, TaxRecord
from doribt.provenance import encode
from doribt.reporting.analysis import finite
from doribt.reporting.benchmark import Benchmark
from doribt.reporting.publish import publish

if TYPE_CHECKING:
    from doribt.reporting.result import BacktestResult

type LedgerRecord = (
    Order
    | Fill
    | IntentRecord
    | CorporateEvent
    | EntitlementRecord
    | TaxRecord
    | TaxLotRecord
    | TaxPayment
)

ACCOUNT_COLUMNS = (
    "session",
    "cash_units",
    "equity_units",
    "available_cash_units",
    "frozen_cash_units",
    "dividend_receivable_units",
    "tax_payable_units",
    "nav",
    "return",
    "drawdown",
)
POSITION_COLUMNS = (
    "session",
    "symbol",
    "quantity",
    "sellable",
    "frozen_quantity",
    "pending_quantity",
    "close_units",
    "value_units",
)


def _json(path: Path, value: object) -> None:
    path.write_text(encode(value) + "\n", encoding="utf-8")


def _csv(path: Path, columns: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: encode(value) if isinstance(value, (list, tuple, dict)) else value
                    for key, value in row.items()
                }
            )


def _account(result: "BacktestResult", folder: Path) -> None:
    _csv(folder / "account.csv", ACCOUNT_COLUMNS, _account_rows(result))
    _csv(folder / "positions.csv", POSITION_COLUMNS, _position_rows(result))


def _account_rows(result: "BacktestResult") -> Iterator[dict[str, Any]]:
    changes, nav, drawdown = result.returns, result.nav, result.drawdown
    for i, session in enumerate(result.sessions):
        yield {
            "session": session.isoformat(),
            "cash_units": int(result.cash_units[i]),
            "equity_units": int(result.equity_units[i]),
            "available_cash_units": max(
                int(
                    result.cash_units[i] - result.tax_payable_units[i] - result.frozen_cash_units[i]
                ),
                0,
            ),
            "frozen_cash_units": int(result.frozen_cash_units[i]),
            "dividend_receivable_units": int(result.dividend_receivable_units[i]),
            "tax_payable_units": int(result.tax_payable_units[i]),
            "nav": float(nav[i]),
            "return": finite(float(changes[i])),
            "drawdown": float(drawdown[i]),
        }


def _position_rows(result: "BacktestResult") -> Iterator[dict[str, Any]]:
    return (
        {
            "session": session.isoformat(),
            "symbol": symbol,
            "quantity": int(result.holdings[i, j]),
            "sellable": int(result.sellable[i, j]),
            "frozen_quantity": int(result.frozen_shares[i, j]),
            "pending_quantity": int(result.pending_shares[i, j]),
            "close_units": int(result.close_units[i, j]),
            "value_units": int(result.holdings[i, j] + result.pending_shares[i, j])
            * int(result.close_units[i, j]),
        }
        for i, session in enumerate(result.sessions)
        for j, symbol in enumerate(result.symbols)
    )


def _ledger(result: "BacktestResult", folder: Path) -> None:
    tables: dict[str, tuple[type[LedgerRecord], tuple[LedgerRecord, ...]]] = {
        "orders": (Order, result.orders),
        "fills": (Fill, result.fills),
        "intents": (IntentRecord, result.intents),
        "entitlements": (EntitlementRecord, result.entitlements),
        "corporate_events": (CorporateEvent, result.corporate_events),
        "taxes": (TaxRecord, result.taxes),
        "tax_lots": (TaxLotRecord, result.tax_lots),
        "tax_payments": (TaxPayment, result.tax_payments),
    }
    for name, (record_type, items) in tables.items():
        rows = (asdict(item) for item in items)
        _csv(folder / f"{name}.csv", [field.name for field in fields(record_type)], rows)
    _ledger_json(folder / "ledger.json", tables)


def _ledger_json(
    path: Path, tables: Mapping[str, tuple[type[LedgerRecord], tuple[LedgerRecord, ...]]]
) -> None:
    # 保留 encode() 的排序、空值及间隔字节，每次只物化一条记录。
    with path.open("w", encoding="utf-8") as stream:
        stream.write("{")
        for index, name in enumerate(sorted(tables)):
            if index:
                stream.write(", ")
            stream.write(encode(name) + ": [")
            for row_index, item in enumerate(tables[name][1]):
                if row_index:
                    stream.write(", ")
                stream.write(encode(asdict(item)))
            stream.write("]")
        stream.write("}\n")


def _file_info(path: Path) -> dict[str, str | int]:
    checksum, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(1_048_576):
            checksum.update(chunk)
            size += len(chunk)
    return {"sha256": checksum.hexdigest(), "bytes": size}


def _benchmark(benchmark: Benchmark, folder: Path) -> None:
    _json(
        folder / "benchmark.json",
        {
            "name": benchmark.name,
            "source": benchmark.source,
            "sessions": list(benchmark.sessions),
            "prices": benchmark.prices,
            "normalization": "first_supplied_close",
            "price_basis": "caller_supplied",
        },
    )


def _manifest(result: "BacktestResult", folder: Path) -> None:
    files = {path.name: _file_info(path) for path in sorted(folder.iterdir())}
    _json(
        folder / "manifest.json",
        {
            "schema": "doribt.export/1",
            "run_fingerprint": result.run_info.fingerprint,
            "data_fingerprint": result.data_fingerprint,
            "units": {
                "money_and_price_units": "0.0001 CNY",
                "income_micros": "0.000001 CNY/share",
                "quantity": "shares",
                "ratios": "decimal (0.1 = 10%)",
            },
            "nulls": {"json": "null", "csv": "empty field"},
            "nested_csv_values": "JSON",
            "files": files,
        },
    )


def export(
    result: "BacktestResult",
    destination: Path,
    *,
    benchmark: Benchmark | None,
    periods_per_year: float | None,
    risk_free_rate: float,
    include_plot: bool,
    daily: bool = False,
) -> Path:
    report = (
        result.report(
            benchmark=benchmark,
            periods_per_year=252 if periods_per_year is None else periods_per_year,
            risk_free_rate=risk_free_rate,
        )
        if daily
        else None
    )
    stats = (
        dict(report.stats)
        if report is not None
        else result.stats(
            benchmark=benchmark, periods_per_year=periods_per_year, risk_free_rate=risk_free_rate
        )
    )
    destination = destination.absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"export destination already exists: {destination}")
    # Require an existing parent; exporting never implicitly creates an arbitrary directory tree.
    parent = destination.parent.resolve(strict=True)
    destination = parent / destination.name
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}-", dir=parent) as temporary:
        folder = Path(temporary)
        _account(result, folder)
        _ledger(result, folder)
        _json(folder / "run.json", result.run_info.to_dict())
        _json(folder / "stats.json", stats)
        _json(
            folder / "research.json",
            {
                "schema": "doribt.research/1",
                "outputs": {name: output.to_dict() for name, output in result.outputs.items()},
            },
        )
        if report is not None:
            _json(folder / "report.json", report.to_dict())
        if benchmark is not None:
            _benchmark(benchmark, folder)
        if include_plot:
            _plot(result, folder, benchmark, daily)
        _manifest(result, folder)
        # Read back the manifest and verify every serialized byte before publication.
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for name, entry in manifest["files"].items():
            if _file_info(folder / name) != entry:
                raise OSError(f"export verification failed: {name}")
        publish(folder, destination)
    return destination


def _plot(result: "BacktestResult", folder: Path, benchmark: Benchmark | None, daily: bool) -> None:
    from doribt.reporting.daily import daily_benchmark, daily_result

    curve = daily_result(result) if daily else result
    base = daily_benchmark(result, benchmark) if daily and benchmark is not None else benchmark
    curve.plot(benchmark=base).savefig(folder / "equity.png", dpi=150)
