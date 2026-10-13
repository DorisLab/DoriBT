# 预计算目标

已有目标数组时，将它交给 `WeightTargets` 或 `PositionTargets`，即可把信号计算与账户执行分开。选择 Numba 后端可加速目标推进和撮合，同时返回完整账户与交易记录。

## 使用预计算目标

```python
from doribt import Backtest, PositionTargets, RunConfig

# quantities 是各收盘时点的目标股数，与 data.timeline 对齐。
targets = PositionTargets(sessions=data.timeline, quantities={symbol: quantities})
result = Backtest(data, config=RunConfig(backend="numba")).run(targets)
```

先安装 `doribt[numba]`，再运行完整示例：

```sh
python examples/minute.py --precomputed --backend numba
```

基础安装可选择 `backend="python"`。两种后端使用相同的目标、账户与结果接口。

## 股数、权重与再平衡

| 目标 | 行为 |
| --- | --- |
| `PositionTargets` | 按股／份声明持仓；数值变化时更新该证券的目标，未列证券保持原目标 |
| `WeightTargets(sizing="close")` | 按决策收盘权益和价格计算股数，从下一 bar 开始执行 |
| `WeightTargets(sizing="execution")` | 按下一 bar 开盘统一估值，定量一次后执行 |
| `WeightTargets(rebalance=True)` | 每根 bar 重新声明权重，按指定时点重算股数 |

目标数组与 `data.timeline` 精确对齐，权重描述整个组合，省略证券为零目标。默认相同权重延续确定后的股数，部分成交和跨日续单都追踪这个数量。更详细的下单和定量示例见[编写策略](guide/strategies.md)。

## 完整编译的场景

使用 Numba、启用 JIT，并通过 `RunConfig`／`BarExecution` 运行无公司行动的行情时，内置股数和权重目标支持：

- 日线、1 分钟和 5 分钟。
- 上市前、停牌及退市后的合法区间。
- 收盘／开盘定量、逐 bar 再平衡、共享现金、T+N、部分成交、费用与三种滑点模型。

未上市且零目标的证券可保留空价格和缺省规则，完整证券轴与意图记录照常保存。非零权重需要定量时，引擎检查当日规则与价格；持仓仍须有有效估值。运行[六日上市示例](examples.md)中的 `inactive_weights.py`，可以观察 A 上市前后与 B 的组合执行。

目标推进、申报、冻结、撮合、交收和估值进入同一编译循环，结束后立即生成完整订单、成交、意图与税务记录。含公司行动的策略、自定义目标子类和普通回调沿用相应的生命周期；Numba 回调可加速撮合，策略函数继续在 Python 中执行。

## 执行计划与缓存

查看一次回测实际使用的路径：

```python
plan = result.run_info.to_dict()["execution_plan"]
print(plan["plan"], plan["actual_backend"], plan["fallback_reasons"])
```

| 字段 | 含义 |
| --- | --- |
| `requested_backend` / `actual_backend` | 请求和实际后端；JIT 关闭时实际使用 Python |
| `jit_enabled` | 是否启用 Numba JIT |
| `plan` | `compiled_targets` 完整目标编译；`scheduled_segments` 分段；`bar_callbacks` 回调 |
| `compiled_scope` | `targets_and_matching` 目标与撮合；`matching` 撮合；`none` |
| `fallback_reasons` | 路径选择原因；完整编译时为空 |

原因码包括 `python_backend`、`jit_disabled`、`corporate_actions`、`custom_target`、`callback`、`legacy_execution` 和 `unsupported_plan`。计划使用 `doribt.execution-plan/1` 格式，并随 `run.json` 导出。

较早的 `execution_path` 字段标识预计算或回调这一执行族，精确编译范围以 `execution_plan` 为准。引擎及依赖版本记录在同一份运行信息的 `versions` 中。

重复实验时，复用同一 `MarketData` 和 `Backtest`，可复用只读行情准备与证券索引；每次 `run` 都创建独立账户。Numba 首次编译后可复用缓存，适合反复比较参数、费用和目标。具体速度见[性能](performance.md)。
