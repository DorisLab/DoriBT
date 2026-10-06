"""Standard tables and canonical metadata, staged before a no-replace publish."""

import csv
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .analysis import finite
from .benchmark import Benchmark
from .orders import Fill, IntentRecord, Order
from .provenance import encode
from .publish import publish
from .rights import CorporateEvent, EntitlementRecord
from .taxes import TaxLotRecord, TaxPayment, TaxRecord

if TYPE_CHECKING:
    from .result import BacktestResult

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


def _json(path: Path, value: object) -> None:
    path.write_text(encode(value) + "\n", encoding="utf-8")


def _csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
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
    changes, nav, drawdown = result.returns, result.nav, result.drawdown
    rows = [
        {
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
        for i, session in enumerate(result.sessions)
    ]
    _csv(folder / "account.csv", list(rows[0]), rows)
    positions = [
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
    ]
    _csv(folder / "positions.csv", list(positions[0]), positions)


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
    records = {}
    for name, (record_type, items) in tables.items():
        rows = [asdict(item) for item in items]
        records[name] = rows
        _csv(folder / f"{name}.csv", [field.name for field in fields(record_type)], rows)
    # This file preserves nulls, types and nested intent adjustments without CSV conventions.
    _json(folder / "ledger.json", records)


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
    files = {
        path.name: {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        for path in sorted(folder.iterdir())
    }
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
) -> Path:
    stats = result.stats(
        benchmark=benchmark, periods_per_year=periods_per_year, risk_free_rate=risk_free_rate
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
        if benchmark is not None:
            _benchmark(benchmark, folder)
        if include_plot:
            result.plot(benchmark=benchmark).savefig(folder / "equity.png", dpi=150)
        _manifest(result, folder)
        # Read back the manifest and verify every serialized byte before publication.
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for name, entry in manifest["files"].items():
            content = (folder / name).read_bytes()
            if (
                len(content) != entry["bytes"]
                or hashlib.sha256(content).hexdigest() != entry["sha256"]
            ):
                raise OSError(f"export verification failed: {name}")
        publish(folder, destination)
    return destination
