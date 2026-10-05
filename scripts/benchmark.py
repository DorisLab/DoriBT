"""Measure full engine runs in fresh processes; no timing thresholds or data downloads."""

import argparse
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import psutil
from benchmark_workloads import portfolio_case, single_case, synthetic_market, verify_backends
from market_case import load_market, write_report


def worker(args: argparse.Namespace) -> None:
    start = time.perf_counter()
    if args.market:
        data, _ = load_market(args.market, args.calendar, args.profile, args.source)
    else:
        data = synthetic_market(args.days, 1)
    load_seconds = time.perf_counter() - start
    single = single_case(data, args.worker, args.repeats, args.parameters)
    start = time.perf_counter()
    portfolio = synthetic_market(args.days, args.assets)
    portfolio_load = time.perf_counter() - start
    report = {
        "backend": args.worker,
        "load_single_seconds": load_seconds,
        "load_portfolio_seconds": portfolio_load,
        "single": single,
        "portfolio": portfolio_case(portfolio, args.worker, args.repeats),
    }
    write_report(args.output, report)


def sample(process: subprocess.Popen[bytes], timeout: float) -> int:
    peak = 0
    observer = psutil.Process(process.pid)
    deadline = time.monotonic() + timeout
    while process.poll() is None:
        if time.monotonic() >= deadline:
            raise TimeoutError("benchmark worker exceeded its time limit")
        try:
            # Windows venv's python.exe can be a redirector with a Python child.
            # Include descendants; summed RSS can double-count shared pages.
            resident = 0
            for member in [observer, *observer.children(recursive=True)]:
                try:
                    resident += member.memory_info().rss
                except psutil.NoSuchProcess:
                    continue
            peak = max(peak, resident)
        except psutil.NoSuchProcess:
            break
        time.sleep(0.005)
    return peak


def child(args: argparse.Namespace, backend: str, folder: Path) -> dict[str, Any]:
    output = folder / f"{backend}.json"
    cache = folder / f"cache-{backend}"
    cache.mkdir()
    env = os.environ.copy()
    env["NUMBA_CACHE_DIR"] = str(cache)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        backend,
        "--output",
        str(output),
        "--days",
        str(args.days),
        "--assets",
        str(args.assets),
        "--repeats",
        str(args.repeats),
        "--parameters",
        str(args.parameters),
    ]
    if args.market:
        command += [
            "--market",
            str(args.market),
            "--calendar",
            str(args.calendar),
            "--profile",
            args.profile,
            "--source",
            args.source,
            "--no-corporate-actions",
        ]
    start = time.perf_counter()
    # Inherit output for immediate failure diagnostics; no buffered pipes to deadlock.
    with subprocess.Popen(command, env=env) as process:
        try:
            peak = sample(process, args.timeout)
            code = process.wait(timeout=5)
        finally:
            if process.poll() is None:
                for descendant in psutil.Process(process.pid).children(recursive=True):
                    try:
                        descendant.kill()
                    except psutil.NoSuchProcess:
                        pass
                process.kill()
                process.wait()
    if code:
        raise subprocess.CalledProcessError(code, command)
    report: dict[str, Any] = json.loads(output.read_text(encoding="utf-8"))
    report.update(
        process_wall_seconds=time.perf_counter() - start,
        sampled_peak_rss_bytes=peak,
        new_numba_cache=True,
    )
    return report


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--days", type=int, default=1455)
    parser.add_argument("--assets", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--parameters", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--market", type=Path)
    parser.add_argument("--calendar", type=Path)
    parser.add_argument("--profile", choices=["sse_equity_etf", "szse_equity_etf"])
    parser.add_argument("--source")
    parser.add_argument("--no-corporate-actions", action="store_true")
    parser.add_argument("--worker", choices=["python", "numba"], help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repeats < 1 or not 1 <= args.parameters <= 100:
        parser.error("repeats/timeout must be positive; parameters must be 1..100")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be finite and positive")
    market_inputs = [
        args.market,
        args.calendar,
        args.profile,
        args.source,
        args.no_corporate_actions,
    ]
    if any(market_inputs) and not all(market_inputs):
        parser.error("market/calendar/profile/source/no-corporate-actions are required together")
    if args.output.exists():
        parser.error("output already exists")
    return args


def main() -> None:
    args = arguments()
    if args.worker:
        worker(args)
        return
    with tempfile.TemporaryDirectory(prefix="doribt-benchmark-") as temporary:
        reports = [child(args, backend, Path(temporary)) for backend in ("python", "numba")]
    signature = verify_backends(reports)
    report = {
        "schema": "doribt.performance/1",
        "reports": reports,
        "verified_result_sha256": signature,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
        },
        "measurement": {
            "rss": (
                "worker process tree summed RSS, external 5 ms sampling; "
                "short peaks may be missed and shared pages may be counted twice"
            ),
            "first": (
                "fresh process, empty Numba cache; includes preparation and JIT, "
                "excludes imports/data load"
            ),
            "warm": "same Backtest, new account each run; result hashing excluded from run timers",
            "parameters": "serial independent accounts; run time sum, no concurrent workers",
            "portfolio": (
                "synthetic shared account; runs after single-asset JIT, "
                "first includes its data preparation"
            ),
        },
    }
    write_report(args.output, report)
    print(f"Verified both backends; saved {args.output}")


if __name__ == "__main__":
    main()
