"""Run a parameterized strategy, compare a benchmark, and export a research report."""

import argparse
import tempfile
from pathlib import Path

from strategies import synthetic_market

from doribt import Backtest, Benchmark, Context


def moving_average(ctx: Context, *, fast: int, slow: int, allocation: float) -> None:
    if not 1 <= fast < slow:
        raise ValueError("windows must satisfy 1 <= fast < slow")
    closes = ctx.history("ALPHA", bars=slow)
    if len(closes) < slow:
        return
    weight = allocation if closes[-fast:].mean() > closes.mean() else 0
    ctx.target_weights({"ALPHA": weight})


def run(output: Path, backend: str, plot: bool) -> None:
    data = synthetic_market()
    result = Backtest(data, initial_cash=100_000).run(
        moving_average, parameters={"fast": 5, "slow": 20, "allocation": 0.95}, backend=backend
    )
    benchmark = Benchmark(
        sessions=data.sessions,
        prices=data.prices("close")[:, 0],
        name="ALPHA price index",
        source=data.source,
    )
    # 252 is an explicit illustration, not inferred from the fictional weekday calendar.
    summary = result.stats(benchmark=benchmark, periods_per_year=252, risk_free_rate=0)
    print("SYNTHETIC: artificial prices/calendar; explicit 252-period annualization.")
    for name in (
        "total_return",
        "max_drawdown",
        "annual_volatility",
        "sharpe",
        "excess_total_return",
    ):
        print(name, summary[name])
    result.export(output, benchmark=benchmark, periods_per_year=252, risk_free_rate=0, plot=plot)
    print("Parameters:", result.run_info.to_dict()["parameters"])
    print("Report:", output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    parser.add_argument(
        "--output", type=Path, help="New directory; existing paths are never overwritten"
    )
    parser.add_argument("--plot", action="store_true", help="Include PNG (requires doribt[plot])")
    args = parser.parse_args()
    if args.output is not None:
        run(args.output, args.backend, args.plot)
    else:
        with tempfile.TemporaryDirectory(prefix="doribt-research-") as temporary:
            run(Path(temporary) / "report", args.backend, args.plot)
        print("Demonstration report cleaned up; use --output to keep one.")


if __name__ == "__main__":
    main()
