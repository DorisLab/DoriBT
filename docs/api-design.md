# API 的使用路径与职责

0.2 开发版增量见[分钟执行](minute-execution.md)：复用 Backtest／Context／MarketData，增加 BarExecution 与一单多次成交；从实验包迁移的示例已统一。下面保留 0.1.0 正式入口的基线说明。

预计算固定股数现可使用 `PositionTargets(sessions=data.timeline, quantities={symbol: values})`；与 WeightTargets 一样保持时间对齐和同一结果接口。分钟场景自动采用[事件分段执行](scheduled-execution.md)，回调路径继续保留。

本文描述 0.1.0 的正式数据入口、共享账户、收盘函数策略、预计算目标、分红送转、指标／图表及标准导出。真实 ETF 对账和完整引擎性能证据见[首版验收](release-0.1.0.md)。后续 API 可以演进，行为变化须进入版本记录。

正式入口为 `Backtest(MarketData, initial_cash=..., costs=Costs(...)).run(strategy, parameters=..., backend=...)`。策略可以是普通收盘函数，或 `WeightTargets`。`parameters` 是实际传给回调的关键字参数，同时以初始快照记入结果；不是仅供展示的附加标签。无参数函数仍可以直接传入。数据提供层构建一次完整对象，策略不重复拼装规则，见[数据契约](data-contract.md)与[执行模型](execution-model.md)。公司行动作为 `MarketData.actions` 的事实输入，策略无需手工派息、拆股或扣税；结果保留应收、待入账股份、权益事件和税务批次，见[权益模型](corporate-actions.md)。不支持的行动影响账户时抛出 `UnsupportedCorporateAction`。

结果直接提供 `nav`、`returns`、`drawdown`、`stats(benchmark=..., periods_per_year=..., risk_free_rate=...)`、`plot(benchmark=...)`、`export(path, ...)`。不要求用户先创建报告管理器、把结果重新变成内核矩阵，或再传一遍初始资金。`run_info.to_dict()` 提供本次运行的来源快照；图表依赖延迟加载。完整口径与导出结构见[结果与研究记录](results.md)。

研究历史默认原始价，`ctx.history(symbol, adjustment="asof")` 可按当前决策时点复权。带来源的单次事件因子由数据准备层通过 `PriceAdjustment` 放入 `MarketData.adjustments`，策略不拼复权表，也不将最新整段前复权数据用于所有历史决策。成交与账户永远读取原始价；权益分配不会因研究视图再计一次。

同一个 `Backtest` 可以连续调用 `run` 比较不同参数；只复用不可变行情的准备结果，每次账户、委托和权益状态独立。调用者自己的有状态策略对象不会自动重置，应为每组参数重新创建或明确初始化。`ctx.bar_index` 为输入日历中从零开始的位置，包含停牌交易日；定期调仓无需为计数读取并复制整段历史。参数批量目前是显式 Python 循环，尚无优化器或并行调度承诺。

## 从用户的研究过程出发

正常路径为：准备有日期和证券标识的数据 → 编写策略 → 配置账户与执行假设 → 运行 → 分析和导出结果。默认使用者不需要知道内核数组的轴顺序、原因码整数值或 Numba 回调签名。

原型预算模型已从开发版移除，历史实现保留在 v0.1.0。均线示例改用正式入口；独立 Decimal 账本、半分舍入和费用可负担性继续由正式引擎测试覆盖。

预计算目标须与行情时点严格对齐；信号自动延迟不能证明因子没有未来数据，仍需前缀稳定性检查。

## 基础引擎应提供的接口

| 职责 | 用户使用方式 | 契约 |
| --- | --- | --- |
| 数据 | 有日期和证券标识的行情表／本地数据集，附交易日历、历史规则状态和公司行动 | 数据适配器负责列映射、时点和来源；规则编译不由每个策略重复实现 |
| 事件策略 | 收盘回调读取历史、账户和订单，提交股数／目标权重意图 | 默认只可见当前时点及之前的数据；策略可维护自身状态，不能直接改写账本 |
| 批量研究 | 显式带时点的信号或目标表，以及独立参数组 | 接入同一执行与账户系统；证券维、参数维有标识，不靠猜测数组形状 |
| 执行 | 选择已实现的成交模型、费用、滑点和资金分配政策 | 下单时点、定量时点、估值时点分别明确；不把固定股数和开盘预算混为一种模型 |
| 结果 | 统一的概要、净值、持仓、订单、成交、费用、诊断、图表与导出 | 自动携带初始资金和运行来源；指标口径及单位明确，单次结果易读，组合和批量结果保持标识 |

先把单标的择时和组合调仓的完整调用体验做通，再根据使用反馈稳定公开 API。不会为了提前给出类图而同时引入尚无消费者的基类、插件注册表和多套配置文件。

## 参考与区别

[Backtesting.py](https://kernc.github.io/backtesting.py/doc/backtesting/backtesting.html) 的回测／策略／结果组织方式、[bt](https://pmorissette.github.io/bt/) 的组合策略表达、[vectorbt](https://vectorbt.dev/api/portfolio/base/) 的分层信号入口，以及 [RQAlpha](https://rqalpha.readthedocs.io/zh-cn/latest/intro/overview.html) 的完整研究流程共同说明：使用体验需要从策略和研究结果设计，编译内核的输入输出应停留在实现边界。这里只借鉴设计，不承诺复刻其语义或兼容其代码。
