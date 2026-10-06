"""One fail-fast quality entry for local development and CI."""

import argparse
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

from check_wheel import check_wheel

ROOT = Path(__file__).resolve().parents[1]


def run(*command: str) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Audit locked runtime + all optional dependencies online",
    )
    args = parser.parse_args()
    if args.backend == "numba" and importlib.util.find_spec("numba") is None:
        raise SystemExit("Numba checks require: uv sync --locked --extra numba")
    run("uv", "lock", "--check")
    run(sys.executable, "scripts/check_size.py")
    run("uv", "run", "--no-sync", "ruff", "check", ".")
    run("uv", "run", "--no-sync", "ruff", "format", "--check", ".")
    run("uv", "run", "--no-sync", "mypy")
    tests = [sys.executable, "-m", "pytest", "--cov", "--cov-report=term-missing"]
    if args.backend == "python":
        tests += ["-m", "not numba"]
    run(*tests)
    run(sys.executable, "examples/sma.py", "--backend", args.backend)
    run(sys.executable, "examples/minute.py", "--backend", args.backend)
    run(sys.executable, "examples/market_data.py")
    run(sys.executable, "examples/strategies.py", "--backend", args.backend)
    run(sys.executable, "examples/dividends.py", "--backend", args.backend)
    run(sys.executable, "examples/historical_rules.py", "--backend", args.backend)
    run(sys.executable, "examples/research.py", "--backend", args.backend, "--plot")
    with tempfile.TemporaryDirectory(prefix="doribt-build-") as temporary:
        run("uv", "build", "--out-dir", temporary)
        wheels = list(Path(temporary).glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("Expected exactly one freshly built wheel")
        check_wheel(wheels[0], args.backend)
    if args.audit:
        run(sys.executable, "scripts/audit.py")
    print(f"Quality checks passed ({args.backend}); dependency audit: {args.audit}")


if __name__ == "__main__":
    main()
