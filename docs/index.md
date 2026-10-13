---
myst:
  html_meta:
    description: "DoriBT 是面向 A 股与 ETF 研究的 Python 回测引擎，集成历史交易规则、共享账户、分钟做 T、Numba 加速和完整研究报告。"
---

# DoriBT：让策略想法成为可解释的回测结果

用 Python 研究 A 股择时、ETF 轮动和分钟做 T。DoriBT 把历史交易规则、共享资金、成交成本与研究报告连成完整流程，让你既能看到收益，也能解释收益从何而来。

**当前版本 0.6.2**，支持 Python 3.13—3.15、Windows 和 Linux。

## 从一个想法开始

| 你想研究什么 | 从这里开始 |
| --- | --- |
| 先跑通一次回测 | [安装](guide/install.md) → [第一次回测](guide/quickstart.md) |
| 在多个 ETF 之间轮动 | [ETF 轮动](tutorials/etf-rotation.md)：动量、共享现金与再平衡 |
| 用底仓做分钟交易 | [分钟做 T](tutorials/intraday-t.md)：T+0、T+1 与可卖数量 |
| 把已有行情变成研究报告 | [数据到报告](tutorials/data-to-report.md)：CSV、DataFrame、指标与导出 |

## 为什么用 DoriBT

- **交易规则进入账户。** T+1、整手、涨跌停、最低佣金、部分成交和分红送转共同决定最终收益。
- **策略就是普通 Python 函数。** 读取历史窗口、声明目标仓位，把精力放在研究逻辑上；已有信号数组可直接交给预计算目标。
- **结果能够逐笔解释。** 从净值下钻到持仓、订单、成交和费用，连未成交原因也有完整记录。
- **反复研究更高效。** Numba 预计算路径将目标与撮合放进编译循环，2520 日 × 100 标的组合的热运行中位数为 0.147 秒。

[进一步了解 DoriBT](comparison.md) · [查看性能](performance.md) · [运行完整示例](examples.md)

```{toctree}
:caption: 使用教程
:maxdepth: 1

安装 <guide/install>
第一次回测 <guide/quickstart>
接入行情 <guide/data>
编写策略 <guide/strategies>
分钟回测 <guide/minutes>
运行配置与参数 <guide/parameters>
分析与导出报告 <guide/reports>
扩展研究输出 <guide/extensions>
可运行示例 <examples>
常见问题 <faq>
```

```{toctree}
:caption: 实战
:maxdepth: 1

ETF 轮动 <tutorials/etf-rotation>
分钟做 T <tutorials/intraday-t>
数据到报告 <tutorials/data-to-report>
```

```{toctree}
:caption: 了解 DoriBT
:maxdepth: 1

为什么选择 DoriBT <comparison>
性能 <performance>
```

```{toctree}
:caption: 接口与口径
:maxdepth: 1

API 参考 <api>
行情与数据 <data-contract>
策略与账户 <execution-model>
分钟成交与滑点 <minute-execution>
市场规则 <china-market>
分红送转与税务 <corporate-actions>
结果与指标 <results>
参数与研究输出 <research-contract>
预计算目标 <scheduled-execution>
```

```{toctree}
:caption: 项目
:maxdepth: 1

开发方向 <roadmap>
接口组织 <api-design>
原生扩展 <native-records>
```

[PyPI](https://pypi.org/project/doribt/) · [GitHub](https://github.com/DorisLab/DoriBT) · [问题反馈](https://github.com/DorisLab/DoriBT/issues) · [文本导航](llms.txt)
