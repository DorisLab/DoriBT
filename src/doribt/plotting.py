"""Optional plotting; the base engine never imports Matplotlib."""

from typing import TYPE_CHECKING

import numpy as np

from .benchmark import Benchmark

if TYPE_CHECKING:
    from matplotlib.figure import Figure

    from .result import BacktestResult


def plot(result: "BacktestResult", benchmark: Benchmark | None) -> "Figure":
    try:
        from matplotlib.figure import Figure
        from matplotlib.ticker import PercentFormatter
    except ImportError as error:
        raise ImportError(
            "Plotting requires the optional dependency: pip install 'doribt[plot]'"
        ) from error
    if benchmark is not None:
        benchmark.validate(result.sessions)
    figure = Figure(figsize=(10, 6), layout="constrained")
    sessions = np.array(result.sessions, dtype="datetime64[D]")
    top = figure.add_subplot(2, 1, 1)
    bottom = figure.add_subplot(2, 1, 2, sharex=top)
    top.plot(sessions, result.nav, label="Strategy", color="#916a28", linewidth=1.8)
    if benchmark is not None:
        top.plot(sessions, benchmark.nav, label=benchmark.name, color="#5080a0", linewidth=1.2)
    top.set(title="DoriBT | Equity and drawdown", ylabel="Net asset value (first close = 1)")
    top.legend(loc="best", frameon=False)
    bottom.fill_between(sessions, -result.drawdown, 0, alpha=0.25, color="#916a28")
    bottom.plot(sessions, -result.drawdown, color="#916a28", linewidth=1)
    bottom.set(ylabel="Drawdown", xlabel="Session")
    bottom.yaxis.set_major_formatter(PercentFormatter(1))
    for axis in (top, bottom):
        axis.grid(axis="y", alpha=0.18)
        axis.spines[["top", "right"]].set_visible(False)
    return figure
