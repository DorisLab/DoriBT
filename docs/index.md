---
myst:
  html_meta:
    description: "DoriBT 中文文档：用 Python 研究 A 股与 ETF 轮动、日线和分钟做 T，接入 CSV/DataFrame 行情并生成可对账的回测报告。"
---

# DoriBT：A 股与 ETF 的 Python 量化回测

用自己的行情，在共享现金账户中编写函数策略或预计算目标，研究日线择时、ETF 轮动和 1／5 分钟做 T，再核对订单、成交、费用与研究报告。本手册对应 **0.6.1**。

**第一次使用：** [安装 Python 3.13 与 DoriBT](guide/install.md) → [运行三日回测并解释收益](guide/quickstart.md) → [接入自己的行情](guide/data.md)。

## 你想完成什么

| 研究任务 | 从这里开始 |
| --- | --- |
| 研究多个 A 股 ETF 的轮动组合 | [ETF 轮动实战](tutorials/etf-rotation.md)：历史窗口、共享资金与再平衡 |
| 分清分钟做 T 与 T+1 可卖约束 | [分钟做 T 实战](tutorials/intraday-t.md)：T+0 ETF、T+1 底仓与逐笔费用 |
| 把已有行情变成可复核的结果 | [CSV／DataFrame 到研究报告](tutorials/data-to-report.md)：字段转换、指标与导出 |
| 判断框架是否适合自己的研究 | [功能与框架比较](comparison.md) · [性能、边界与复现](performance.md) |
| 排查不成交、费用或收益口径 | [常见问题](faq.md) · [API 参考](api.md) |

支持 Python 3.13、Windows／Linux；基础依赖 NumPy，可选 Numba 和 Matplotlib。现金账户预设核验范围为 2015-09-09 至 2026-10-12，科创板从 2019-07-22 起。数据、日历、证券身份与涨跌停价由调用者提供；完整资产和执行边界见[市场规则](china-market.md)。不提供行情下载或实盘接口，公开示例采用人工行情。

[PyPI](https://pypi.org/project/doribt/) · [GitHub](https://github.com/DorisLab/DoriBT) · [全部示例](examples.md) · [问题反馈](https://github.com/DorisLab/DoriBT/issues) · [文本导航](llms.txt)

```{toctree}
:caption: 开始使用
:maxdepth: 1

guide/install
guide/quickstart
guide/data
guide/strategies
faq
```

```{toctree}
:caption: 完成一次研究
:maxdepth: 1

tutorials/etf-rotation
tutorials/intraday-t
tutorials/data-to-report
guide/minutes
guide/parameters
guide/reports
guide/extensions
examples
```

```{toctree}
:caption: 选型与性能
:maxdepth: 1

comparison
performance
native-records
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
