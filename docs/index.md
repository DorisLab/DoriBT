---
myst:
  html_meta:
    description: "DoriBT：A 股与 ETF 的轻量高性能回测框架。历史交易规则开箱即用，Numba 快速回放，完整交易账本；接入自有行情，用普通 Python 函数研究策略。"
---

# DoriBT：A 股与 ETF 轻量回测

**交易规则开箱即用，预计算回测接近向量化速度，每笔交易都有账可查。**

接入已有行情，用普通 Python 函数研究 A 股择时、ETF 轮动和分钟做 T。基础包只依赖 NumPy，加速和图表按需安装；从目标仓位到完整研究报告，都在自己的 Python 脚本中完成。

**当前版本 0.6.2**，支持 Python 3.13—3.15、Windows 和 Linux。

## 从一个想法开始

| 你想研究什么 | 从这里开始 |
| --- | --- |
| 先跑通一次回测 | [安装](guide/install.md) → [第一次回测](guide/quickstart.md) |
| 在多个 ETF 之间轮动 | [ETF 轮动](tutorials/etf-rotation.md)：动量、共享现金与再平衡 |
| 用底仓做分钟交易 | [分钟做 T](tutorials/intraday-t.md)：T+0、T+1 与可卖数量 |
| 把已有行情变成研究报告 | [数据到报告](tutorials/data-to-report.md)：CSV、DataFrame、指标与导出 |

## 为什么用 DoriBT

- **规则已经备好。** 按证券分类和历史日期选择 A 股／ETF 规则，T+0／T+1、数量、历史税费与分红送转进入账户执行。
- **长历史也能快速试验。** 2520 日 × 100 标的组合的 Numba 热回放中位数为 **0.147 秒**；已有信号数组可直接运行。
- **接入轻量，结果完整。** 策略写成普通函数，多标的共享现金；净值、持仓、订单、成交和费用一起返回，直接分析与导出。

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
