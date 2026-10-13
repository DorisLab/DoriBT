# DoriBT：A 股与 ETF 的轻量高性能回测框架

**A 股／ETF 交易规则开箱即用，预计算回测接近向量化速度，每笔交易都有账可查。**

接入已有 CSV 或 DataFrame，写一个普通 Python 函数，就能研究 **A 股择时、ETF 轮动和 1／5 分钟做 T**。DoriBT 把历史规则、共享资金、成交成本和研究报告放进一个轻量 Python 包，让你从策略想法直接走到完整回测。

[使用手册](https://dorislab.github.io/DoriBT/) · [安装](https://pypi.org/project/doribt/) · [为什么选择 DoriBT](https://dorislab.github.io/DoriBT/comparison.html) · [性能](https://dorislab.github.io/DoriBT/performance.html)

## 为什么选择 DoriBT

- **A 股与 ETF 规则已经备好。** `china_rules` 按证券分类和历史日期提供 T+0／T+1、数量规则、印花税与过户费；账户处理涨跌停成交阻断、最低佣金、部分成交和分红送转。接入行情后，把精力放在策略上。
- **把长历史变成快速迭代。** Numba 将预计算目标与撮合放入编译循环；2520 日 × 100 标的组合热回放只需 **0.147 秒**，适合反复比较参数、成本和仓位。
- **轻量接入，完整交付。** 基础包只依赖 NumPy，策略写成普通函数，组合在同一个现金账户中运行。回测结束即可查看现金、持仓和逐笔交易，导出 CSV／JSON，按需生成图表。

当前发行版 **0.6.2**，支持 **Python 3.13—3.15、Windows 和 Linux**。新环境推荐 Python 3.15。

## 安装与第一次回测

```sh
python -m pip install "doribt==0.6.2"
# 同时安装加速和图表：
python -m pip install "doribt[numba,plot]==0.6.2"
```

下面用三日人工行情完成一次买入持有回测。保存为 `quickstart.py`，运行 `python quickstart.py`，即可看到 **10895 元**期末权益：995 元现金，加上 900 份持仓 × 11 元收盘价。

```python
"""安装 doribt 后即可运行；仅使用合成行情与公开 API。"""

from doribt import Backtest, Context, Costs, Instrument, MarketData, RunConfig, china_rules

days = ["2025-01-02", "2025-01-03", "2025-01-06"]
prices = [10, 10, 11]
data = MarketData.from_records(
    [
        {
            "session": day,
            "symbol": "DEMO",
            "status": "trading",
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 500_000,
            "upper_limit": 12,
            "lower_limit": 8,
        }
        for day, price in zip(days, prices, strict=True)
    ],
    calendar=days,
    instruments=[Instrument(symbol="DEMO", kind="etf")],
    rules=china_rules({"DEMO": "szse_equity_etf"}, start=days[0], end=days[-1]),
    source="人工三日行情，仅用于演示",
)


def buy_and_hold(ctx: Context) -> None:
    ctx.target_weights({"DEMO": 0.9})


config = RunConfig(initial_cash=10_000, costs=Costs(commission=0.0003, minimum_commission=5))
result = Backtest(data, config=config).run(buy_and_hold)
print("期末权益：", result.equity[-1])  # 10895 元：剩余现金 995 + 持仓 900 × 11。
print("总收益率：", result.report().stats["total_return"])
```

[第一次回测](https://dorislab.github.io/DoriBT/guide/quickstart.html)逐步解释成交时点、最低佣金和收益。

## 做一份完整研究

- [ETF 轮动](https://dorislab.github.io/DoriBT/tutorials/etf-rotation.html)：比较动量，在共享账户中换仓。
- [分钟做 T](https://dorislab.github.io/DoriBT/tutorials/intraday-t.html)：理解 T+0、T+1 和昨日底仓。
- [数据到报告](https://dorislab.github.io/DoriBT/tutorials/data-to-report.html)：接入 CSV／DataFrame，分析并导出结果。

[接入行情](https://dorislab.github.io/DoriBT/guide/data.html) · [编写策略](https://dorislab.github.io/DoriBT/guide/strategies.html) · [分析与导出](https://dorislab.github.io/DoriBT/guide/reports.html) · [API](https://dorislab.github.io/DoriBT/api.html) · [全部示例](https://github.com/DorisLab/DoriBT/tree/main/examples)

## 性能

同一份 2520 日 × 100 标的组合输入，固定股数目标，热运行中位数如下；计时包含引擎运行及现金、持仓、权益和逐笔成交输出。

| 实现 | 热运行耗时 |
| --- | ---: |
| DoriBT Python | 0.9704 秒 |
| DoriBT Numba | 0.1470 秒 |
| vectorbt Numba | 0.09553 秒 |
| vectorbt Rust | 0.07533 秒 |
| Backtrader | 18.9645 秒 |
| Zipline-reloaded | 7.1511 秒 |

在这个日线组合场景中，DoriBT 的回放已接近 vectorbt Numba 的速度；另外 17 个与 vectorbt 的日线／分钟对照场景中，DoriBT Numba 有 **10 个更快**。完整账户与逐笔记录随运行一起返回。选择 DoriBT，你可以同时获得快速试验、现成的 A 股／ETF 规则和能够追查每次成交的结果。

0.6.2 的长历史面板测试中，三组重复研究回放累计由 **63.82 秒降到 40.57 秒，节省约 36% 的回放时间**。[性能页](https://dorislab.github.io/DoriBT/performance.html)提供分钟场景、首次运行、Python 版本和完整复现资料。

## 参与开发

欢迎提交研究需求、最小复现和交易规则改进。

```sh
git clone https://github.com/DorisLab/DoriBT.git
cd DoriBT
uv sync --locked --extra numba
uv run --no-sync python scripts/check.py --backend numba --audit
```

[贡献说明](CONTRIBUTING.md) · [质量检查](docs/quality.md) · [问题反馈](https://github.com/DorisLab/DoriBT/issues)

采用 [Apache-2.0](LICENSE) 许可证。
