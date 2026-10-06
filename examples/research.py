"""Run a parameterized strategy, compare a benchmark, and export a research report."""

import argparse
import tempfile
from pathlib import Path

from strategies import synthetic_market

from doribt import (
    Backtest,
    Benchmark,
    Context,
    Metric,
    Parameter,
    ParameterSet,
    ResearchOutput,
    RunConfig,
    Table,
)

PARAMETERS = ParameterSet(
    {
        "fast": Parameter(
            type="int", default=5, minimum=2, maximum=50, step=1, label="短均线", unit="bars"
        ),
        "slow": Parameter(
            type="int", default=20, minimum=5, maximum=200, step=1, label="长均线", unit="bars"
        ),
        "allocation": Parameter(
            type="float",
            default=0.95,
            minimum=0,
            maximum=1,
            step=0.05,
            label="目标仓位",
            unit="ratio",
        ),
    }
)


def moving_average(ctx: Context, *, fast: int, slow: int, allocation: float) -> None:
    if not 1 <= fast < slow:
        raise ValueError("windows must satisfy 1 <= fast < slow")
    closes = ctx.history("ALPHA", bars=slow)
    if len(closes) < slow:
        return
    weight = allocation if closes[-fast:].mean() > closes.mean() else 0
    ctx.record(fast=float(closes[-fast:].mean()), slow=float(closes.mean()), target_weight=weight)
    ctx.target_weights({"ALPHA": weight})


def run(output: Path, backend: str, plot: bool) -> None:
    data = synthetic_market()
    # Same JSON-compatible values a client form can send; zero minimum is also valid.
    config = RunConfig.from_dict(
        {"initial_cash": 100_000, "commission": 0.0002, "minimum_commission": 1, "backend": backend}
    )
    result = Backtest(data, config=config).run(
        moving_average, parameter_schema=PARAMETERS, parameters={"fast": 5}
    )
    result = result.analyze(
        "diagnostics",
        lambda r: ResearchOutput(
            metrics={
                "fees_per_fill": Metric(
                    sum(fill.fees for fill in r.fills) / len(r.fills) if r.fills else None,
                    unit="CNY",
                    description="Average transaction fees per fill",
                )
            },
            tables={
                "parameters": Table(
                    columns=["name", "value"],
                    rows=[
                        {"name": key, "value": value}
                        for key, value in r.run_info.to_dict()["parameters"].items()
                    ],
                )
            },
        ),
    )
    benchmark = Benchmark(
        sessions=data.sessions,
        prices=data.prices("close")[:, 0],
        name="ALPHA price index",
        source=data.source,
    )
    # 252 is an explicit illustration, not inferred from the fictional weekday calendar.
    summary = result.report(benchmark=benchmark).stats
    print("SYNTHETIC: artificial prices/calendar; explicit 252-period annualization.")
    for name in (
        "total_return",
        "max_drawdown",
        "annual_volatility",
        "sharpe",
        "excess_total_return",
        "win_rate",
        "turnover",
    ):
        print(name, summary[name])
    result.export(output, benchmark=benchmark, daily=True, plot=plot)
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
