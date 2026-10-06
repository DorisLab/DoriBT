# DoriBT

面向 A 股研究的 Python 回测引擎，支持日线与 1／5 分钟现金账户回测。

[文档中心](https://dorislab.github.io/DoriBT/) · [PyPI](https://pypi.org/project/doribt/) · [使用教程](https://dorislab.github.io/DoriBT/guide/quickstart.html)

- 多标的共享资金、T+1、历史交易规则和分红送转。
- 部分成交、可配置佣金与最低佣金、成交量参与率和滑点。
- 函数策略与预计算目标，参数声明、自定义指标和研究输出。
- 日频报告、基准与超额收益、图表和可对账的 CSV／JSON 导出。
- NumPy 基础引擎，可选 Numba 加速和 Matplotlib 绘图。

## 安装

支持 Python 3.13，Windows 和 Linux。

```sh
python -m pip install doribt
# 可选加速与图表：
python -m pip install "doribt[numba,plot]"
```

## 第一次回测

下例使用人工行情，无需账号或行情服务。收盘提交目标，下一根 bar 开盘尝试成交；价格、日历与状态由调用者提供。

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

保存为 `quickstart.py`，运行 `python quickstart.py`，期末权益应为 **10895 元**。

## 示例与参考

完整示例位于 [examples](https://github.com/DorisLab/DoriBT/tree/main/examples)：买入持有、均线、组合轮动、分钟订单、权益处理、参数化研究与报告。

[数据输入](https://dorislab.github.io/DoriBT/guide/data.html) · [策略编写](https://dorislab.github.io/DoriBT/guide/strategies.html) · [分钟回测](https://dorislab.github.io/DoriBT/guide/minutes.html) · [结果与导出](https://dorislab.github.io/DoriBT/guide/reports.html) · [API 参考](https://dorislab.github.io/DoriBT/api.html)

原始价用于成交与账户记账，按决策时点复权的价格用于研究。规则预设覆盖 2020–2025 沪深普通股票与境内股票 ETF；自定义规则须提供适用区间和来源。不提供行情下载或实盘接口，不覆盖盘口排队、融资融券、期货期权与 ETF 申赎。

## 参与开发

```sh
git clone https://github.com/DorisLab/DoriBT.git
cd DoriBT
uv sync --locked --extra numba
uv run --no-sync python scripts/check.py --backend numba --audit
```

开发检查见 [贡献说明](https://github.com/DorisLab/DoriBT/blob/main/CONTRIBUTING.md)与[质量门禁](https://github.com/DorisLab/DoriBT/blob/main/docs/quality.md)。CI 仅在 milestone／release 运行，普通提交和 PR 不触发。欢迎提供最小复现、规则依据及聚焦的改进；维护者按实际需要推进，不承诺支持时限或 API 稳定性。

采用 [Apache-2.0](https://github.com/DorisLab/DoriBT/blob/main/LICENSE) 许可证。
