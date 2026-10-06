# API 参考

所有对象通过 `from doribt import ...` 导入。下列签名在构建文档时直接读取已安装的包，中文说明补充单位和使用约束。返回记录及指标字段另见[结果参考](results.md)。

## 回测与配置

```{eval-rst}
.. autoclass:: doribt.Backtest
```

传入验证后的行情与 `config=RunConfig(...)`。同一个实例可重复运行，每次新建账户。不要将 `config` 与独立的 `initial_cash`／`costs`／`execution` 混用。

```{eval-rst}
.. automethod:: doribt.Backtest.run
```

`strategy` 是普通函数或预计算目标；参数以关键字传给策略。`backend` 可覆盖配置中选择的后端，实际值写入运行信息。

```{eval-rst}
.. autoclass:: doribt.RunConfig
```

```{eval-rst}
.. automethod:: doribt.RunConfig.from_dict
```

```{eval-rst}
.. automethod:: doribt.RunConfig.to_dict
```

```{eval-rst}
.. automethod:: doribt.RunConfig.schema
```

运行配置的默认值和 JSON 字段见[参数教程](guide/parameters.md)。

```{eval-rst}
.. autoclass:: doribt.Costs
```

佣金以小数比例输入，最低佣金以元输入，允许零。使用 RunConfig 时滑点放在 `BarExecution`，`Costs.slippage_ticks` 保持零。

```{eval-rst}
.. autoclass:: doribt.BarExecution
```

`slippage_policy="strict"` 拒绝越界，`"cap"` 截到行情边界，`"cost"` 保留完整滑点成本；日线和分钟都适用。成交资格、用户限价及资金约束继续有效，完整语义见[滑点契约](minute-execution.md)。旧日线 `Costs.slippage_ticks` 路径不提供该选择；需要配置时使用 `RunConfig(execution=BarExecution(...))`。

```{eval-rst}
.. autoclass:: doribt.FixedTicks
```

```{eval-rst}
.. autoclass:: doribt.FixedBps
```

```{eval-rst}
.. autoclass:: doribt.VolumeImpact
```

参与率取 `(0, 1]`；ticks 为整数档位，bps 为基点，VolumeImpact 为参与率平方的冲击系数。规则与失败语义见[执行模型](minute-execution.md)。

## 行情与规则

```{eval-rst}
.. automethod:: doribt.MarketData.from_records
```

```{eval-rst}
.. automethod:: doribt.MarketData.from_csv
```

```{eval-rst}
.. automethod:: doribt.MarketData.from_minutes
```

```{eval-rst}
.. automethod:: doribt.MarketData.prices
```

`calendar` 为严格递增的独立交易日历。`sessions` 是唯一交易日，`timeline` 是完整 bar 时间轴，`symbols` 保留声明顺序。`prices` 返回只读价格矩阵。字段和空值规则见[数据契约](data-contract.md)。

```{eval-rst}
.. autoclass:: doribt.Instrument
```

```{eval-rst}
.. autofunction:: doribt.china_rules
```

```{eval-rst}
.. autoclass:: doribt.TradingRule
```

```{eval-rst}
.. autoclass:: doribt.RulePeriod
```

```{eval-rst}
.. autoclass:: doribt.RuleBook
```

```{eval-rst}
.. automethod:: doribt.MinuteClock.build
```

股票／ETF 分类、价位、数量、交收和适用日期见[市场规则](china-market.md)。`MinuteClock` 为已知交易日生成网格，不生成节假日日历。

```{eval-rst}
.. autoclass:: doribt.CorporateAction
```

```{eval-rst}
.. autoclass:: doribt.PriceAdjustment
```

行动日期、应税金额及因子的可知时点见[公司行动](corporate-actions.md)与[研究价格](data-contract.md#按决策时点复权的研究视图)。

## 策略上下文与目标

Context 由引擎传入，不由策略自行构造。`ctx.account`、`orders`、`intents` 提供当前视图，`session`、`now`、`bar_index` 定位当前已完成 bar。

```{eval-rst}
.. automethod:: doribt.Context.history
```

```{eval-rst}
.. automethod:: doribt.Context.order
```

```{eval-rst}
.. automethod:: doribt.Context.cancel_order
```

```{eval-rst}
.. automethod:: doribt.Context.target_positions
```

```{eval-rst}
.. automethod:: doribt.Context.target_weights
```

```{eval-rst}
.. automethod:: doribt.Context.cancel
```

```{eval-rst}
.. automethod:: doribt.Context.record
```

数量以股／份计；单笔数量有符号，目标数量非负。固定订单返回 order_id，持续目标返回 intent_id。撤销和有效期见[执行契约](execution-model.md)。

```{eval-rst}
.. autoclass:: doribt.WeightTargets
```

```{eval-rst}
.. autoclass:: doribt.PositionTargets
```

目标完整对齐 `data.timeline`；不可将参数维当成证券维。详见[预计算执行](scheduled-execution.md)。

## 参数与研究扩展

```{eval-rst}
.. autoclass:: doribt.Parameter
```

```{eval-rst}
.. autoclass:: doribt.ParameterSet
```

```{eval-rst}
.. automethod:: doribt.ParameterSet.to_dict
```

```{eval-rst}
.. automethod:: doribt.ParameterSet.resolve
```

类型、默认值、范围、步长与选项在执行前校验，跨字段逻辑由策略检查。

```{eval-rst}
.. autoclass:: doribt.ResearchOutput
```

```{eval-rst}
.. autoclass:: doribt.Metric
```

```{eval-rst}
.. autoclass:: doribt.Series
```

```{eval-rst}
.. autoclass:: doribt.Table
```

指标带单位与说明；曲线对齐完整结果，表格为统一列的 JSON 标量行。详见[扩展教程](guide/extensions.md)。

## 结果分析与导出

BacktestResult 由 `run` 返回，账户金额便利属性以元计，`*_units` 为万分之一元的整数；时间在行，证券在列。

```{eval-rst}
.. autoclass:: doribt.Benchmark
```

```{eval-rst}
.. automethod:: doribt.BacktestResult.stats
```

```{eval-rst}
.. automethod:: doribt.BacktestResult.report
```

```{eval-rst}
.. automethod:: doribt.BacktestResult.plot
```

```{eval-rst}
.. automethod:: doribt.BacktestResult.export
```

```{eval-rst}
.. automethod:: doribt.BacktestResult.analyze
```

```{eval-rst}
.. automethod:: doribt.BacktestResult.with_outputs
```

```{eval-rst}
.. automethod:: doribt.ResearchReport.to_dict
```

`stats` 保留 bar 口径，`report` 默认日频；`export(daily=True)` 同步导出报告。自定义输出返回新对象，不覆盖现有命名空间。默认字段、指标定义与文件列表见[结果参考](results.md)。
