"""Load a normalized private minute snapshot and verify against a Decimal reference."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from numpy.typing import NDArray

from doribt import Backtest, BarExecution, Context, FixedTicks, Instrument, MarketData, china_rules
from doribt.provenance import encode


def load(folder: Path) -> MarketData:
    with (folder / "calendar.csv").open(encoding="utf-8-sig", newline="") as stream:
        calendar = [row["session"] for row in csv.DictReader(stream)]
    with (folder / "market.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    symbols = sorted({row["symbol"] for row in rows})
    if len(symbols) != 1:
        raise ValueError("minute case requires exactly one domestic equity ETF")
    return MarketData.from_minutes(
        rows,
        calendar=calendar,
        instruments=[Instrument(symbol=symbols[0], kind="etf")],
        rules=china_rules({symbols[0]: "szse_equity_etf"}, start=calendar[0], end=calendar[-1]),
        source="caller-supplied raw minute ETF snapshot",
    )


def signals(
    data: MarketData, fast: int = 60, slow: int = 240, size: int = 10000
) -> NDArray[np.int64]:
    """At 09:45 each day compare completed-bar SMAs, hold fixed shares until next decision."""
    if not 0 < fast < slow:
        raise ValueError("windows require 0 < fast < slow")
    prices = data.prices("close")[:, 0]
    total = np.r_[0.0, np.cumsum(prices)]
    targets = np.zeros(len(prices), dtype=np.int64)
    target = 0
    for index, point in enumerate(data.timeline):
        if (
            index >= slow - 1
            and getattr(point, "hour", 0) == 9
            and getattr(point, "minute", 0) == 45
        ):
            end = index + 1
            target = (
                size
                if (total[end] - total[end - fast]) / fast > (total[end] - total[end - slow]) / slow
                else 0
            )
        targets[index] = target
    return targets


class FixedTargets:
    """Known target sequence; emit only changes, preserving each active intention."""

    def __init__(self, symbol: str, values: NDArray[np.int64]) -> None:
        self.symbol, self.values = symbol, values

    def __call__(self, ctx: Context) -> None:
        index = ctx.bar_index
        if index == 0 or self.values[index] != self.values[index - 1]:
            ctx.target_positions({self.symbol: int(self.values[index])})


def main() -> None:
    from minute_reference import reference, verify

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--backend", choices=("python", "numba"), default="python")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    started = perf_counter()
    data = load(args.folder)
    prepared = perf_counter() - started
    targets = signals(data)
    test = Backtest(data, execution=BarExecution(participation=0.001, slippage=FixedTicks(1)))
    started = perf_counter()
    result = test.run(FixedTargets(data.symbols[0], targets), backend=args.backend)
    elapsed = perf_counter() - started
    expected = reference(data, targets)
    verify(result, expected)
    payload = dict(
        backend=args.backend,
        bars=len(data.timeline),
        days=len(data.sessions),
        prepare_seconds=prepared,
        run_seconds=elapsed,
        stats=result.stats(),
        input_sha256={
            name: hashlib.sha256((args.folder / name).read_bytes()).hexdigest()
            for name in ("market.csv", "calendar.csv")
        },
        ledger_sha256=hashlib.sha256(encode(expected).encode()).hexdigest(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encode(payload) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
