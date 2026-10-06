"""One fresh process per engine; normalization and verification are outside warm timing."""

import argparse
import importlib
import json
import statistics
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
from numpy.typing import NDArray

from doribt import Backtest, BarExecution, FixedTicks, MarketData

case = importlib.import_module("scripts.minute_case")
load: Callable[[Path], MarketData] = case.load
signals: Callable[..., NDArray[np.int64]] = case.signals
reference: Callable[[MarketData, NDArray[np.int64]], dict[str, Any]] = importlib.import_module(
    "scripts.minute_reference"
).reference


def market_array(data: MarketData) -> NDArray[np.int64]:
    return np.array(
        [
            [
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                10,
                data.day_index(i),
                int(bar.phase == "auction"),
                bar.upper_limit or 0,
                bar.lower_limit or 0,
            ]
            for i, bar in enumerate(data.bars)
        ],
        dtype=np.int64,
    )


def verify(data: MarketData, target: NDArray[np.int64], result: dict[str, Any]) -> str:
    import hashlib

    expected = reference(data, target)
    for name in ("cash", "holdings", "equity"):
        actual = result[name][:, 0]
        units = actual if name == "holdings" else actual * 10000
        if not np.allclose(units, expected[name], atol=0.0001, rtol=0):
            index = int(np.flatnonzero(np.abs(units - expected[name]) > 0.0001)[0])
            raise ValueError(
                f"{name} differs from Decimal at {index}: {units[index]} != {expected[name][index]}"
            )
    times = {str(point): index for index, point in enumerate(data.timeline)}
    fills = [[times[row[0]], row[1], row[2], row[3]] for row in expected["fills"]]
    if result["fills"] != fills:
        raise ValueError("fill rows differ from independent Decimal reference")
    return hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()


def own(test: Backtest, target: NDArray[np.int64], backend: str) -> dict[str, Any]:
    times = {point: index for index, point in enumerate(test.data.timeline)}
    result = test.run(case.FixedTargets(test.data.symbols[0], target), backend=backend)
    return dict(
        cash=result.cash[:, None],
        equity=result.equity[:, None],
        holdings=result.holdings,
        fills=[
            [times[f.timestamp or f.session], f.quantity, f.price_units, f.commission_units]
            for f in result.fills
        ],
    )


def vbt_column(result: dict[str, Any], column: int) -> dict[str, Any]:
    records = result["fills"]
    rows = records[records["col"] == column]
    return {
        name: result[name][:, column : column + 1] for name in ("cash", "holdings", "equity")
    } | {
        "fills": [
            [
                int(row["idx"]),
                int(row["size"]) * (1 if row["side"] == 0 else -1),
                int(round(row["price"] * 10000)),
                int(round(row["fees"] * 10000)),
            ]
            for row in rows
        ]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--engine", choices=("python", "numba", "vectorbt"), required=True)
    parser.add_argument("--batch", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.batch <= 20 or args.repeats < 1:
        raise ValueError("batch must be 1..20 and repeats positive")
    start = perf_counter()
    data = load(args.folder)
    targets = [signals(data, fast=30 + index * 10) for index in range(args.batch)]
    matrix, prices = np.column_stack(targets), market_array(data)
    prepared = perf_counter() - start
    test = Backtest(data, execution=BarExecution(participation=0.001, slippage=FixedTicks(1)))
    if args.engine == "vectorbt":
        adapter = importlib.import_module("benchmarks.minute.vectorbt_adapter")

        def run_single() -> dict[str, Any]:
            return vbt_column(adapter.run(prices, matrix[:, :1]), 0)

        def run_batch() -> list[dict[str, Any]]:
            result = adapter.run(prices, matrix)
            return [vbt_column(result, i) for i in range(args.batch)]
    else:

        def run_single() -> dict[str, Any]:
            return own(test, targets[0], args.engine)

        def run_batch() -> list[dict[str, Any]]:
            return [own(test, target, args.engine) for target in targets]

    start = perf_counter()
    result = run_single()
    first = perf_counter() - start
    ledger = verify(data, targets[0], result)
    warm = []
    for _ in range(args.repeats):
        start = perf_counter()
        result = run_single()
        warm.append(perf_counter() - start)
    verify(data, targets[0], result)
    # Warm the batch shape before measuring it, including vectorbt array-layout specialization.
    results = run_batch()
    batch_hashes = [
        verify(data, target, result) for target, result in zip(targets, results, strict=True)
    ]
    batch_times = []
    for _ in range(args.repeats):
        start = perf_counter()
        results = run_batch()
        batch_times.append(perf_counter() - start)
    for target, result in zip(targets, results, strict=True):
        verify(data, target, result)
    print(
        json.dumps(
            dict(
                engine=args.engine,
                bars=len(data.timeline),
                batch=args.batch,
                prepared_seconds=prepared,
                first_run_seconds=first,
                warm_seconds=warm,
                warm_median_seconds=statistics.median(warm),
                batch_seconds=batch_times,
                batch_median_seconds=statistics.median(batch_times),
                ledger_sha256=ledger,
                batch_ledger_sha256=batch_hashes,
                versions={name: version(name) for name in ("numpy", "numba")},
                vectorbt_version=version("vectorbt") if args.engine == "vectorbt" else None,
            )
        )
    )


if __name__ == "__main__":
    main()
