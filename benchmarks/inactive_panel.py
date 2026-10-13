"""公开人工面板：非活动比例、证券数和 Python 版本的可复现端到端计时。"""

import argparse
import hashlib
import json
import os
import platform
import threading
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import asdict, fields
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any
from unittest.mock import patch

import numpy as np
import psutil

from doribt import (
    Backtest,
    BacktestResult,
    BarExecution,
    Costs,
    Instrument,
    MarketData,
    RuleBook,
    RulePeriod,
    TradingRule,
    WeightTargets,
)
from doribt.kernels.compiled import PreparedData, prepare
from doribt.kernels.scheduled_loop import compiled_schedule
from doribt.runtime.compiled_schedule import execute
from doribt.serialization import encode


class CompiledTiming:
    """只测量已选择的完整编译路径，不参与路径选择；分项已包含在总计时中。"""

    def __init__(self) -> None:
        self.values: dict[str, float] = {}
        self.factory = compiled_schedule
        self.execute = execute
        self.prepare = prepare
        self.stack = ExitStack()

    def prepare_inputs(self, data: MarketData) -> PreparedData:
        started = perf_counter()
        result = self.prepare(data)
        self.values["numeric_prepare_seconds"] = perf_counter() - started
        return result

    def kernel_factory(self) -> Any:
        kernel = self.factory()

        def call(*args: Any) -> Any:
            started = perf_counter()
            result = kernel(*args)
            self.values["kernel_seconds"] = perf_counter() - started
            self.values["_kernel_end"] = perf_counter()
            return result

        return call

    def run(self, *args: Any) -> BacktestResult:
        result = self.execute(*args)
        if "_kernel_end" in self.values:
            self.values["records_and_result_seconds"] = perf_counter() - self.values.pop(
                "_kernel_end"
            )
        return result

    def install(self) -> None:
        self.stack.enter_context(
            patch("doribt.runtime.compiled_schedule.compiled_schedule", self.kernel_factory)
        )
        self.stack.enter_context(patch("doribt.runtime.compiled_schedule.execute", self.run))
        self.stack.enter_context(patch("doribt.runtime.engine.prepare", self.prepare_inputs))

    def restore(self) -> None:
        self.stack.close()


def panel(days: int, width: int, inactive: float) -> tuple[MarketData, WeightTargets, float, float]:
    started = perf_counter()
    calendar = tuple(date(2020, 1, 2) + timedelta(days=i) for i in range(days))
    symbols = tuple(f"S{i:04}" for i in range(width))
    listings = np.linspace(0, int(days * inactive), width, dtype=int)
    rule = TradingRule(
        price_tick=".01",
        buy_minimum=100,
        buy_step=100,
        sell_step=1,
        settlement_days=1,
        stamp_duty_sell=0,
        transfer_fee=".00001",
    )
    periods = tuple(
        RulePeriod(
            symbol=symbol,
            start=calendar[int(listing)],
            end=calendar[-1],
            rule=rule,
            source="人工上市规则",
            version="1",
        )
        for symbol, listing in zip(symbols, listings, strict=True)
    )
    rows = []
    for index, day in enumerate(calendar):
        for column, symbol in enumerate(symbols):
            active = index >= listings[column]
            price = 10 + column % 11 if active else None
            suspended = active and index % 29 == 13
            rows.append(
                dict(
                    session=day,
                    symbol=symbol,
                    status="suspended" if suspended else "trading" if active else "unlisted",
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=100_000 if active and not suspended else 0,
                    upper_limit=None,
                    lower_limit=None,
                )
            )
    data = MarketData.from_records(
        rows,
        calendar=calendar,
        instruments=[Instrument(symbol=s, kind="etf") for s in symbols],
        rules=RuleBook(periods),
        source="公开人工面板；非交易所日历和真实证券",
    )
    preparation = perf_counter() - started
    started = perf_counter()
    weight = (1_000_000 // width) / 1_000_000
    target = WeightTargets(
        sessions=data.timeline,
        weights={
            symbol: [
                weight if i >= listings[column] and (i // 21 + column) % 2 else 0
                for i in range(days)
            ]
            for column, symbol in enumerate(symbols)
        },
    )
    return data, target, preparation, perf_counter() - started


def digest(result: BacktestResult) -> str:
    payload: dict[str, Any] = {}
    for item in fields(result):
        if item.name in ("backend", "run_info"):
            continue
        value = getattr(result, item.name)
        if isinstance(value, np.ndarray):
            value = value.tolist()
        elif isinstance(value, Mapping):
            value = dict(value)
        elif isinstance(value, tuple) and value and hasattr(value[0], "__dataclass_fields__"):
            value = [asdict(record) for record in value]
        payload[item.name] = value
    return hashlib.sha256(encode(payload).encode()).hexdigest()


class PeakMemory:
    def __init__(self) -> None:
        self.bytes = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self) -> None:
        process = psutil.Process()
        while not self.stop.wait(0.02):
            try:
                self.bytes = max(
                    self.bytes,
                    sum(p.memory_info().rss for p in [process, *process.children(recursive=True)]),
                )
            except psutil.Error:
                continue


def measure(args: argparse.Namespace, timing: CompiledTiming) -> dict[str, object]:
    data, targets, preparation, target_time = panel(args.days, args.symbols, args.inactive)
    samples: list[dict[str, object]] = []
    identities: dict[str, object] = {}
    expected: str | None = None
    backends = ("python", "numba") if args.backend == "both" else (args.backend,)
    for repeat in range(args.repeats + 1):
        for backend in backends if repeat % 2 == 0 else backends[::-1]:
            # 每次重新建 Backtest；计时包含数值准备、来源、内核与完整记录创建。
            test = Backtest(
                data,
                initial_cash=1_000_000,
                costs=Costs(commission=".0003", minimum_commission=5),
                execution=BarExecution(participation=".1"),
            )
            timing.values.clear()
            started = perf_counter()
            result = test.run(targets, backend=backend)
            elapsed = perf_counter() - started
            actual = digest(result)
            if expected is not None and actual != expected:
                raise RuntimeError(f"完整账本不同：{backend} repeat={repeat}")
            expected = actual
            info = result.run_info.to_dict()
            identities[backend] = {
                key: info[key] for key in ("versions", "engine_sha256", "execution_plan")
            }
            samples.append(
                dict(
                    backend=backend,
                    repeat=repeat,
                    seconds=elapsed,
                    orders=len(result.orders),
                    fills=len(result.fills),
                    intents=len(result.intents),
                    **timing.values,
                )
            )
    summaries = {}
    for backend in backends:
        warm = [
            float(str(s["seconds"])) for s in samples if s["backend"] == backend and s["repeat"]
        ]
        summaries[backend] = dict(
            median=float(np.median(warm)),
            p10=float(np.quantile(warm, 0.1)),
            p90=float(np.quantile(warm, 0.9)),
            total_seconds=sum(warm),
        )
    return dict(
        input=dict(
            days=args.days,
            symbols=args.symbols,
            inactive_max=args.inactive,
            fingerprint=data.fingerprint,
        ),
        market_prepare_seconds=preparation,
        target_construction_seconds=target_time,
        complete_ledger_sha256=expected,
        samples=samples,
        summaries=summaries,
        identities=identities,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=252)
    parser.add_argument("--symbols", type=int, default=50)
    parser.add_argument("--inactive", type=float, default=0.6)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--backend", choices=["both", "python", "numba"], default="both")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.days < 2 or args.symbols < 1 or not 0 <= args.inactive < 1 or args.repeats < 1:
        parser.error("至少 2 个日期、1 只证券、1 次预热后重复；非活动比例须在 [0,1)。")
    if args.output.exists():
        parser.error("输出文件已存在，请选择新的路径。")
    memory = PeakMemory()
    timing = CompiledTiming()
    timing.install()
    memory.thread.start()
    try:
        report = measure(args, timing)
    finally:
        timing.restore()
        memory.stop.set()
        memory.thread.join()
    report["environment"] = dict(
        platform=platform.platform(),
        python=platform.python_version(),
        cpu=platform.processor(),
        cache=os.environ.get("NUMBA_CACHE_DIR"),
        threads={
            key: os.environ.get(key)
            for key in ("NUMBA_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        },
        process_tree_peak_rss_bytes=memory.bytes,
        sample_interval_seconds=0.02,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["summaries"], ensure_ascii=False))


if __name__ == "__main__":
    main()
