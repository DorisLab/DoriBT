# DoriBT：A 股与 ETF 的 Python 回测引擎

面向中国量化研究者：用自己的行情，在共享现金账户中研究 **A 股／ETF 轮动、日线择时和 1／5 分钟做 T**，并核对每笔订单、成交、费用与持仓。

[文档中心](https://dorislab.github.io/DoriBT/) · [PyPI](https://pypi.org/project/doribt/) · [框架选型](https://dorislab.github.io/DoriBT/comparison.html) · [性能与复现](https://dorislab.github.io/DoriBT/performance.html)

## 能做什么

- **按市场制度回测**：历史 T+0／T+1 预设、按证券与日期覆盖规则、整手约束、分红送转
- **模拟共享资金与成交**：多标的账户、部分成交、最低佣金、成交量参与率、滑点与撤单
- **直接编写研究逻辑**：函数策略、历史窗口、预计算目标与参数声明，无需继承策略基类
- **解释并导出结果**：完整订单／成交账本、日频报告、基准与超额收益、自定义指标、CSV／JSON 与图表
- **按负载选择后端**：NumPy 基础安装，可选 Numba；首次编译与预热性能分开衡量

当前发行版 **0.6.1**，支持 **Python 3.13、Windows／Linux**。引擎不提供行情下载或实盘接口；不覆盖盘口排队、融资融券、期货期权与 ETF 申赎。完整范围见[市场规则](https://dorislab.github.io/DoriBT/china-market.html)。

## 安装与第一次回测

```sh
python -m pip install "doribt==0.6.1"
# 可选 Numba 加速与图表：
python -m pip install "doribt[numba,plot]==0.6.1"
```

下例无需行情账号。保存为 `quickstart.py`，运行 `python quickstart.py`，期末权益应为 **10895 元**。收盘提交目标，下一根 bar 开盘尝试成交。

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

为什么是 10895 元，以及如何避免最后一根 bar 无法成交，见[第一次回测](https://dorislab.github.io/DoriBT/guide/quickstart.html)。

## 按研究任务上手

- [A 股 ETF 轮动：历史窗口、共享资金与再平衡](https://dorislab.github.io/DoriBT/tutorials/etf-rotation.html)
- [分钟做 T：T+0 ETF 与 T+1 底仓的区别](https://dorislab.github.io/DoriBT/tutorials/intraday-t.html)
- [CSV／DataFrame 行情到研究报告](https://dorislab.github.io/DoriBT/tutorials/data-to-report.html)

[数据输入](https://dorislab.github.io/DoriBT/guide/data.html) · [策略编写](https://dorislab.github.io/DoriBT/guide/strategies.html) · [结果与导出](https://dorislab.github.io/DoriBT/guide/reports.html) · [API 参考](https://dorislab.github.io/DoriBT/api.html) · [全部示例](https://github.com/DorisLab/DoriBT/tree/main/examples)

## 性能一览

下表整理已归档测量，精确测试版本与原始结果保留在[复现材料](https://github.com/DorisLab/DoriBT/tree/main/engineering/benchmarks/documentation-20261013)中。

同一组 **2520 个交易日 × 100 标的**的合成日线组合输入，单账户、固定股数目标，禁用费用、T+1、涨跌停和公司行动，使用 XNYS 日历，预热单次中位耗时如下。各框架适配器的现金、持仓、权益和逐笔成交已核对；框架原生市场规则与输出范围并不完全相同，这不是所有策略的速度排名。

| 实现 | 预热单次耗时（秒） |
| --- | ---: |
| DoriBT Python | 0.9704 |
| DoriBT Numba | 0.1470 |
| DoriBT Numba＋可选原生扩展 | 0.1406 |
| vectorbt Numba | 0.09553 |
| vectorbt Rust | 0.07533 |
| Backtrader | 18.9645 |
| Zipline-reloaded | 7.1511 |

该日线场景没有调用原生记录物化路径，0.1470 与 0.1406 秒的差异不能归因于原生扩展。vectorbt 在这组输入上更快；更大分钟负载、完整研究流程、冷启动、机器环境和计时边界见[性能页与公开复现数据](https://dorislab.github.io/DoriBT/performance.html)。

## 数据与制度边界

原始价用于成交和账户记账，按决策时点复权的价格用于研究。现金账户规则预设核验范围为 2015-09-09 至 2026-10-12；科创板从 2019-07-22 起。每日涨跌停、上市与停复牌由输入提供，自定义规则须注明适用区间与来源。示例使用人工行情，演示结果不代表实际策略收益。

## 参与开发

```sh
git clone https://github.com/DorisLab/DoriBT.git
cd DoriBT
uv sync --locked --extra numba
uv run --no-sync python scripts/check.py --backend numba --audit
```

详见[贡献说明](CONTRIBUTING.md)与[质量门禁](docs/quality.md)。欢迎带有最小复现、规则依据与预期行为的问题反馈。采用 [Apache-2.0](LICENSE) 许可证。
