# 接口组织

公开使用路径为：**准备 MarketData → 编写策略 → 配置 RunConfig → Backtest.run → 分析结果**。所有公开对象从 `doribt` 顶层导入，无需依赖内部目录或继承策略基类。

| 对象 | 职责 |
| --- | --- |
| `MarketData` | 行情、时间轴、证券、历史规则和公司行动 |
| `RunConfig` | 资金、佣金、成交模型、滑点和后端 |
| `Context` | 当前已完成历史、账户视图、订单和研究记录 |
| `WeightTargets`／`PositionTargets` | 显式对齐的预计算目标 |
| `BacktestResult` | 每根 bar 的账户、订单、成交、运行来源和扩展输出 |
| `ResearchReport` | 日频统计、月收益和交易盈亏 |

策略参数与运行配置分别表达；研究输出不会反向修改账户。参数批量使用独立账户，证券组合使用共享账户。市场事实、费用假设与指标年化约定分别保存。

源码按 `market`、`accounting`、`runtime`、`kernels`、`reporting`、`research` 组织，内部模块不作为用户依赖入口。具体签名见[API 参考](api.md)，开发检查见[贡献说明](https://github.com/DorisLab/DoriBT/blob/main/CONTRIBUTING.md)。
