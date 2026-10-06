"""运行参数化策略，对比基准并导出研究报告。"""

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
        raise ValueError("均线窗口必须满足 1 <= fast < slow")
    closes = ctx.history("ALPHA", bars=slow)
    if len(closes) < slow:
        return
    weight = allocation if closes[-fast:].mean() > closes.mean() else 0
    ctx.record(fast=float(closes[-fast:].mean()), slow=float(closes.mean()), target_weight=weight)
    ctx.target_weights({"ALPHA": weight})


def run(output: Path, backend: str, plot: bool) -> None:
    data = synthetic_market()
    # 可直接接收客户端表单的 JSON 配置；最低佣金也允许设为零。
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
                    description="每笔成交的平均交易费用",
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
        name="ALPHA",
        source=data.source,
    )
    # 明确采用 252 个交易日的年化假设，不从人工工作日日历推断。
    summary = result.report(benchmark=benchmark).stats
    print("合成示例：使用人工价格与日历，明确按 252 个交易日年化。")
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
    print("策略参数：", result.run_info.to_dict()["parameters"])
    print("报告目录：", output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    parser.add_argument("--output", type=Path, help="保存到新目录，不覆盖已有路径")
    parser.add_argument("--plot", action="store_true", help="导出 PNG 图表（需要 doribt[plot]）")
    args = parser.parse_args()
    if args.output is not None:
        run(args.output, args.backend, args.plot)
    else:
        with tempfile.TemporaryDirectory(prefix="doribt-research-") as temporary:
            run(Path(temporary) / "report", args.backend, args.plot)
        print("临时示例报告已清理；使用 --output 可保存报告。")


if __name__ == "__main__":
    main()
