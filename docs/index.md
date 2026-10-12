# DoriBT

面向 A 股研究的 Python 回测引擎。用自己的行情，编写函数策略或预计算目标，运行日线与 1／5 分钟回测，查看成交、账户和研究报告。

**从一次能解释结果的回测开始：** [安装](guide/install.md) → [第一次回测](guide/quickstart.md) → [接入数据](guide/data.md) → [编写策略](guide/strategies.md)。

| 研究任务 | 对应能力 |
| --- | --- |
| 个股或 ETF 择时 | 历史窗口、目标仓位、T+1、费用和滑点 |
| 多标的轮动 | 共享资金、先卖后买、显式再平衡 |
| 分钟执行模拟 | 部分成交、成交量参与率、订单有效期与撤单 |
| 分钟做 T | 原生 T+0 ETF、日期化规则覆盖与 T+1 底仓约束 |
| 比较研究结果 | 日频报告、基准、超额、自定义指标和 CSV／JSON 导出 |

支持 Python 3.13，Windows／Linux；基础依赖 NumPy，可选 Numba 和 Matplotlib。
现金账户预设核验范围为 2015-09-09 至 2026-10-12，科创板从 2019-07-22 起；
支持按证券与日期覆盖 T+0/T+1 等字段，完整资产与执行边界见[市场规则](china-market.md)。
引擎不提供行情下载或实盘接口；公开示例采用人工行情。

[PyPI](https://pypi.org/project/doribt/) · [GitHub](https://github.com/DorisLab/DoriBT) · [示例](examples.md) · [问题反馈](https://github.com/DorisLab/DoriBT/issues)

```{toctree}
:caption: 使用教程
:maxdepth: 1

guide/install
guide/quickstart
guide/data
guide/strategies
guide/minutes
guide/parameters
guide/reports
guide/extensions
examples
faq
```

```{toctree}
:caption: 接口与口径
:maxdepth: 1

api
data-contract
execution-model
minute-execution
china-market
corporate-actions
results
research-contract
scheduled-execution
```

```{toctree}
:caption: 项目
:maxdepth: 1

roadmap
api-design
```
