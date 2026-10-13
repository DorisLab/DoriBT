---
myst:
  html_meta:
    description: "比较 DoriBT、vectorbt、Backtrader 与 Zipline-reloaded 的研究入口、A 股历史规则、共享资金、审计输出和适用场景。"
---

# 回测框架选型：DoriBT、vectorbt、Backtrader 与 Zipline

先按交易规则、研究方式和所需输出选择，再用自己的负载测量速度。本页比较当前
**DoriBT 0.6.1** 与其他项目的公开能力；外部资料核对日期为 **2026-10-13**。
vectorbt 指[开源社区版](https://github.com/polakowo/vectorbt)，不把 VectorBT PRO
的专有功能算入；Zipline 指 [zipline-reloaded](https://github.com/stefan-jansen/zipline-reloaded)
分支。功能随版本变化，迁移时仍应核对实际安装版本。

## 按研究目标选择

| 框架 | 适合优先评估的需求 | 策略与数据入口 |
| --- | --- | --- |
| DoriBT | 在明确的沪深现金账户范围内研究历史规则、日线／1／5 分钟交易与可对账结果 | `MarketData`＋普通函数策略／`WeightTargets`／`PositionTargets`，通过 `Backtest(...).run(...)` 执行；见[策略教程](guide/strategies.md) |
| vectorbt 开源版 | 将多标的、参数组合和信号组织成数组，比较大量研究配置 | pandas／NumPy 与广播；`Portfolio.from_orders`、`from_signals`，也有支持状态依赖逻辑的 `from_order_func` 回调；见[组合 API](https://vectorbt.dev/api/portfolio/base/) |
| Backtrader | 通过策略类、指标和经纪模型扩展事件驱动流程，组合多个数据源或周期 | `Cerebro` 组织 `Strategy`、Data Feed 和 Broker；提供 `optstrategy` 参数优化入口；见[Cerebro](https://www.backtrader.com/docu/cerebro/)与[功能说明](https://www.backtrader.com/home/features/) |
| Zipline-reloaded | 组织带证券元数据和交易日历的研究数据，并将因子筛选接入事件驱动策略 | 数据 bundle、`initialize`／`handle_data`／定时函数，以及 Pipeline 的 Factor／Filter／Classifier；见[教程](https://zipline.ml4trading.io/beginner-tutorial.html)、[数据接入](https://zipline.ml4trading.io/bundles.html)与[Pipeline API](https://zipline.ml4trading.io/api-reference.html#pipeline-api) |

DoriBT 已提供参数声明、自定义指标和研究输出，但参数组合比较、样本外与滚动验证
仍属于[后续方向](roadmap.md)，不应把它当成现成的批量优化工作台。它也不提供行情下载
或实盘连接。若需要这些流程，选型时应计入数据接入与研究工具的建设成本。

## A 股历史规则：预设与扩展能力分开看

DoriBT 的 `china_rules` 提供有日期范围的沪深现金账户预设：整手／数量上限、价格
最小变动、买入后的可卖延迟、股票印花税和过户费。核验范围是 **2015-09-09 至
2026-10-12**，科创板从 **2019-07-22** 起；`RuleOverride` 可按证券或分类及日期覆盖
字段，并保留来源。具体股票／ETF 分类和限制见[市场规则](china-market.md)。

这不等于自动获得完整市场事实：证券身份、当期跨境 ETF 回转资格、交易日历、每日
涨跌停价和停复牌状态仍需由调用者核对和输入。成交采用下一根 bar 开盘模型，
不模拟盘口队列、集合竞价撮合、融资融券、期货期权或 ETF 申赎。

其他框架提供不同的通用扩展入口：

- vectorbt 可传入费用、滑点和数量参数，也可用自定义订单回调表达状态相关约束；
  [组合 API](https://vectorbt.dev/api/portfolio/base/)同时支持共享现金，并非只能计算独立信号收益
- Backtrader 可扩展[佣金模型](https://www.backtrader.com/docu/commission-schemes/commission-schemes/)，
  并配置 Broker 的滑点和[成交量填充器](https://www.backtrader.com/docu/broker/)
- Zipline-reloaded 提供[佣金与滑点接口](https://zipline.ml4trading.io/api-reference.html)，
  数据 bundle 的 adjustment writer 可接收拆股、合并、现金分红与股票分红；
  见[公司行动输入](https://zipline.ml4trading.io/bundles.html#adjustment-writer)

上述官方资料展示的是通用机制，未给出与 DoriBT 上述范围相同的 A 股历史规则包。
这不是“不能回测 A 股”的结论；采用第三方适配器或自建模型时，应单独检查历史
费率断点、T+1 批次、零股、最低佣金、涨跌停与公司行动的实现和测试。

## 账户、记录与复核

四者都有账户或交易结果，不能用“有无账本”简单区分。更有用的问题是：记录哪些
状态、能否解释每次成交、怎样保留输入与假设，以及需要补建多少导出流程。

| 框架 | 已提供的相关机制 | 选型时需要核对 |
| --- | --- | --- |
| DoriBT | 多标的共享现金；以整数万分之一元记账；逐 bar 现金、持仓、可卖量与冻结，关联意图／订单／成交，公司行动和税务记录；CSV／JSON、运行来源及文件哈希；见[执行模型](execution-model.md)、[权益处理](corporate-actions.md)与[结果契约](results.md) | 是否接受其现金账户、成交时点和税务政策范围；仍需自行保存原始数据、脚本与环境，来源指纹不能捕获任意回调外部状态 |
| vectorbt 开源版 | `cash_sharing` 组合分组、现金／持仓路径、订单／交易／持仓／日志记录及统计图表；见[组合记录与分组](https://vectorbt.dev/api/portfolio/base/) | 采用哪种模拟入口，是否启用所需日志；自定义约束与项目审计导出如何实现 |
| Backtrader | Broker 管理现金和持仓，策略接收订单／交易通知；Analyzer 分析结果，Writer 输出所选数据；见[Broker](https://www.backtrader.com/docu/broker/)、[Analyzers](https://www.backtrader.com/docu/analyzers/analyzers/)与[Writer](https://www.backtrader.com/docu/writer/) | 自定义经纪与费用模型是否覆盖目标市场；需要哪些 Analyzer、通知记录和导出字段 |
| Zipline-reloaded | 结果 DataFrame 包含账户指标、持仓、订单和成交，`record` 保存自定义序列；见[结果教程](https://zipline.ml4trading.io/beginner-tutorial.html) | bundle 的证券生命周期与调整数据是否齐全；目标市场的成交和费用模型，以及运行环境与数据版本如何保存 |

对同一策略，至少先核对信号可知时点、成交价、费用、部分成交、共享资金顺序及公司
行动，再比较净值。收益相近不代表账户路径一致；导出字段丰富也不等于已验证全部市场规则。

## 性能结论的适用范围

本页不按“向量化”或“事件驱动”标签排名。负载规模、成交密度、Python 回调、
编译预热、结果物化和导出范围都会改变耗时与内存。已有可复核测量、比较入口、
输出一致性检查及限制集中在[性能与复现](performance.md)，本页不重复成绩表。

历史测量只证明记录中的版本、机器与场景；不代表当前安装包重新实测，也不构成
对 Backtrader、Zipline-reloaded 或所有 vectorbt 用法的速度结论。实际选择前，
应使用自己的数据与策略，先对齐行为和输出，再分别测冷启动、热运行及峰值内存。
