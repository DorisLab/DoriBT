"""Compare full minute runs in fresh processes and sample total process-tree RSS."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parents[2]


def rss(pid: int) -> int:
    try:
        process = psutil.Process(pid)
        children = [process, *process.children(recursive=True)]
    except psutil.Error:
        return 0
    total = 0
    for child in children:
        try:
            total += child.memory_info().rss
        except psutil.Error:
            continue
    return total


def measure(
    python: Path, folder: Path, output: Path, engine: str, batch: int, repeats: int
) -> dict[str, Any]:
    env = dict(os.environ)
    cache = output / f"cache-{engine}"
    cache.mkdir()
    env["NUMBA_CACHE_DIR"] = str(cache)
    command = [
        str(python),
        "-m",
        "benchmarks.minute.worker",
        str(folder),
        "--engine",
        engine,
        "--batch",
        str(batch),
        "--repeats",
        str(repeats),
    ]
    log = output / f"{engine}.log"
    start = time.perf_counter()
    peak = 0
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=stream)
        while process.poll() is None:
            peak = max(peak, rss(process.pid))
            time.sleep(0.005)
    if process.returncode:
        raise RuntimeError(f"{engine} failed; see {log}")
    result: dict[str, Any] = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    result["worker_wall_seconds"] = time.perf_counter() - start
    result["worker_peak_rss_mib"] = peak / 1024**2
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []
    for engine in ("python", "numba", "vectorbt"):
        result = measure(
            args.python.resolve(), args.folder.resolve(), output, engine, args.batch, args.repeats
        )
        if results and result["batch_ledger_sha256"] != results[0]["batch_ledger_sha256"]:
            raise ValueError("engines disagree on independent batch ledgers")
        results.append(result)
        print(
            engine,
            "warm",
            result["warm_median_seconds"],
            "batch",
            result["batch_median_seconds"],
            flush=True,
        )
    payload = dict(
        platform=platform.platform(),
        cpu=platform.processor(),
        cores=psutil.cpu_count(logical=False),
        threads=psutil.cpu_count(),
        ram_bytes=psutil.virtual_memory().total,
        results=results,
        input_sha256={
            name: hashlib.sha256((args.folder / name).read_bytes()).hexdigest()
            for name in ("market.csv", "calendar.csv")
        },
        source_sha256={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(__file__).parent.glob("*.py")
        },
    )
    (output / "report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(output / "report.json", flush=True)


if __name__ == "__main__":
    main()
