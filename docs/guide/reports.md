# 分析与导出报告

使用 [research.py](../examples.md#参数化研究) 完成一次均线研究：

```sh
python examples/research.py --plot --output my-report
```

它使用人工双证券行情、参数声明、最低佣金 1 元，并以 ALPHA 价格作为基准。需要 `doribt[plot]`；目标目录必须尚不存在。省略 `--output` 时只演示临时导出，运行结束后清理。

## 读取结果

| 需要什么 | 入口 |
| --- | --- |
| 日频收益、Sharpe、回撤、换手率、胜率 | `result.report().stats` |
| 日末账户、月收益、交易成本与盈亏 | `result.report().daily / monthly / trades` |
| 每根 bar 的权益、现金、持仓、可卖量 | `result.equity / cash / holdings / sellable` |
| 未成交原因、订单及逐笔成交 | `result.intents / orders / fills` |
| 参数、执行假设、数据指纹与依赖版本 | `result.run_info.to_dict()` |

默认 `report()` 按日末采样，以每年 252 个交易日、零无风险利率计算；首日收益相对初始资金，包含首日成本。可以显式改变年化假设。未定义的指标返回 `None`，JSON 导出为 `null`。

`stats()` 按原始输入 bar 分析，不默认年化；分钟结果通常应先用 `report()`。所有指标的详细定义见[结果参考](../results.md)。

## 基准与图表

```python
from doribt import Benchmark

# data、result 来自本次回测；这里比较同一证券的原始价格路径。
benchmark = Benchmark(
    sessions=data.timeline,
    prices=data.prices("close")[:, 0],
    name="自备基准",
    source="说明价格指数或全收益指数的来源",
)
report = result.report(benchmark=benchmark)
print(report.stats["excess_total_return"])
figure = result.plot(benchmark=benchmark)
figure.savefig("comparison.png")
```

策略净值红、基准蓝、累计超额金、回撤浅红。累计超额为策略累计收益减基准累计收益。返回的 Matplotlib Figure 可继续编辑或导出 SVG／PDF。

基准须精确对齐，不自动下载或填充；日频报告也接受与唯一交易日对齐的日线基准。基准是理论价格路径，不额外模拟交易费用。

## 保存研究

```python
result.export("new-report", benchmark=benchmark, daily=True, plot=True)
```

`daily=True` 输出 `report.json`，并使统计与图表采用日频口径；`account.csv` 和 `positions.csv` 仍保留全部 bar。订单、成交、权益事件、参数与自定义输出均保存到同一目录，`manifest.json` 包含文件校验和。

父目录须存在，目标目录须不存在；导出失败会清理本次暂存，不覆盖已有报告。完整文件列表及单位见[导出契约](../results.md#导出契约)。
