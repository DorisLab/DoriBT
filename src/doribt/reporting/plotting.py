"""可选图表；基础引擎不会导入 Matplotlib。"""

from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

from doribt.reporting.benchmark import Benchmark

if TYPE_CHECKING:
    from matplotlib.figure import Figure

    from doribt.reporting.result import BacktestResult


def _chinese_font() -> str | None:
    from matplotlib.font_manager import fontManager

    available = set(fontManager.get_font_names())
    candidates = (
        "Noto Sans CJK SC",
        "Noto Sans SC",
        "Microsoft YaHei",
        "PingFang SC",
        "Source Han Sans SC",
        "SimHei",
        "WenQuanYi Zen Hei",
    )
    return next((family for family in candidates if family in available), None)


def plot(result: "BacktestResult", benchmark: Benchmark | None) -> "Figure":
    try:
        from matplotlib.figure import Figure
        from matplotlib.ticker import PercentFormatter
    except ImportError as error:
        raise ImportError("绘图需要可选依赖：pip install 'doribt[plot]'") from error
    if benchmark is not None:
        benchmark.validate(result.sessions)
    font = _chinese_font()
    title, strategy, nav, drawdown, session, time = (
        ("DoriBT｜净值与回撤", "策略净值", "净值（初始资金 = 1）", "回撤", "交易日", "时间")
        if font
        else (
            "DoriBT | Equity and drawdown",
            "Strategy",
            "Net asset value (initial cash = 1)",
            "Drawdown",
            "Session",
            "Time",
        )
    )
    figure = Figure(figsize=(10, 6), layout="constrained")
    # 保留带时区的分钟时点，避免转成 datetime64[D] 后同日的点挤在一起。
    sessions = np.asarray(result.sessions, dtype=object)
    top = figure.add_subplot(2, 1, 1)
    bottom = figure.add_subplot(2, 1, 2, sharex=top)
    top.plot(sessions, result.nav, label=strategy, color="#c83932", linewidth=1.8)
    if benchmark is not None:
        top.plot(sessions, benchmark.nav, label=benchmark.name, color="#7a828e", linewidth=1.2)
    top.set_title(title, fontfamily=font)
    top.set_ylabel(nav, fontfamily=font)
    top.legend(loc="best", frameon=False, prop={"family": font} if font else None)
    bottom.fill_between(sessions, -result.drawdown, 0, alpha=0.25, color="#27845b")
    bottom.plot(sessions, -result.drawdown, color="#27845b", linewidth=1)
    first = result.sessions[0]
    timezone = first.tzinfo if isinstance(first, datetime) else None
    bottom.xaxis.axis_date(tz=timezone)
    bottom.set_ylabel(drawdown, fontfamily=font)
    bottom.set_xlabel(
        f"{time} ({first.tzname()})" if isinstance(first, datetime) else session,
        fontfamily=font,
    )
    bottom.yaxis.set_major_formatter(PercentFormatter(1))
    for axis in (top, bottom):
        axis.grid(axis="y", color="#7a828e", alpha=0.18)
        axis.spines[["top", "right"]].set_visible(False)
    return figure
