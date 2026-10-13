# 常见问题

## 为什么没有成交

先看 `result.orders` 的 `status`、`reason`、`remaining`，再根据 `order_id` 查 `fills`。常见原因：数量不合法、无可卖量、现金不足、停牌、零量、触及价格边界、滑点超出 bar 高低或参与率不足。

最后一根 bar 的信号没有下一根执行机会。`next_bar` 只尝试一次；要在当日等待多次成交可用 `day`，要跨日维持仓位目标可用 `target_positions`／`target_weights`。

## 同一个 80% 仓位为什么没有每天调仓

相同权重与定量模式保持原股数目标。需要重新分配时，调用 `ctx.target_weights(..., rebalance=True)`；默认按当前收盘定量，也可以指定 `sizing="execution"`，按下一 bar 开盘估值定量。整手、费用和成交条件仍可能使实际权重偏离目标，见[策略教程](guide/strategies.md)。

## 佣金和交易软件的结果不一样

在 `Costs` 中明确佣金比例和最低佣金，并检查是否重复计入印花税、过户费。DoriBT 以订单累计成交额计算最低佣金，费用按分舍入；分日生成的目标子单各自计算。请按你使用的券商费率填写这两个参数。

## 能直接输入前复权数据吗

成交和记账使用原始价，策略历史窗口可使用 `adjustment="asof"` 的复权视图。分别输入公司行动和事件因子，分红就会进入账户，连续价格用于研究，见[行情与数据](data-contract.md)。

## 分钟回测为什么没有年化指标

`stats()` 按输入 bar 统计。通常使用 `report()` 按日末汇总，默认 252 个交易日／年；如需逐 bar 年化，为 `stats(periods_per_year=...)` 提供与你的数据相符的周期数。

## 为什么 Numba 没有更快

首次调用要编译；行情准备、Python 回调、密集订单和完整账本构建也占用时间。先查看
`result.run_info.to_dict()["execution_plan"]`：`compiled_targets` 表示目标与撮合进入完整编译，
`scheduled_segments` 表示分段调度，`bar_callbacks` 表示逐 bar 回调。预计算目标通常最适合完整编译；将已有信号交给 `WeightTargets` 或 `PositionTargets`，并复用同一份行情。具体配置见[预计算目标](scheduled-execution.md)。

## 如何选取回测时间和基准

先在数据准备阶段选取所需行情、完整日历、规则与相关公司行动，构造 `MarketData`。基准通过 `Benchmark` 传给分析接口。开始前需要指标预热时，把预热数据纳入输入，并在策略中明确何时开始下单；报告仍覆盖完整输入期。

## 如何迁移现有策略

迁移现有策略时，把行情转换为 `MarketData`，将研究逻辑写成接收 `Context` 的函数，再用 `order` 或目标仓位接口表达交易。数据、参数和下单方式分别见[接入行情](guide/data.md)、[运行配置](guide/parameters.md)和[编写策略](guide/strategies.md)。

## 导出失败或中文图表缺字

导出前创建父目录，并选择新的报告目录名。图表需安装 `doribt[plot]`；Linux 图表缺字时安装 `fonts-noto-cjk`，具体步骤见[安装说明](guide/install.md)。
