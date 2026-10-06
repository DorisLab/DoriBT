# 运行配置与策略参数

**运行配置**决定账户和成交假设；**策略参数**决定研究逻辑。两者分别保存到 `result.run_info`。

## 运行配置

```python
from doribt import BarExecution, Costs, FixedTicks, RunConfig

config = RunConfig(
    initial_cash=300_000,
    costs=Costs(commission=0.0001, minimum_commission=0),
    execution=BarExecution(participation=0.1, slippage=FixedTicks(1)),
    backend="python",
)
```

将它传入 `Backtest(data, config=config)`。佣金比例为小数，`0.0001` 表示万一，最低佣金以元计且允许为零。印花税、过户费按市场历史规则输入，避免把券商打包费率重复计费。

| JSON 字段 | 默认值 | 单位或含义 |
| --- | --- | --- |
| `initial_cash` | 100000 | 人民币元，必须为正 |
| `commission` | 0.0003 | 双向佣金比例 |
| `minimum_commission` | 5 | 单订单累计最低佣金，元 |
| `participation` | 0.05 | 每证券每 bar 最大成交比例 |
| `slippage_kind` | ticks | ticks／bps／volume_impact |
| `slippage_value` | 0 | 档位／基点／冲击系数 |
| `backend` | python | python／numba |

`config.to_dict()` 可保存 JSON；`RunConfig.from_dict(values)` 校验并重建配置。
`RunConfig.schema().to_dict()` 提供类型、默认值、范围和单位，可用于客户端表单。开始／结束时间、证券及周期属于已准备的 `MarketData`，基准属于结果分析。

## 声明策略参数

```{literalinclude} ../../examples/research.py
:language: python
:start-at: PARAMETERS =
:end-before: def moving_average
```

```{literalinclude} ../../examples/research.py
:language: python
:pyobject: moving_average
```

调用 `Backtest(data, config=config).run(moving_average, parameter_schema=PARAMETERS, parameters={"fast": 5})`。未填写值使用声明的默认值，参数作为关键字传给策略；未知键、错误类型、越界或步长不符在首次回调前失败。`fast < slow` 等跨字段关系由策略检查。

声明支持 int／float／str／bool；步长从 minimum（未指定则 0）起算。不使用声明时，也可通过 `parameters` 传递 JSON 对象和列表。

## 对比多个参数

显式循环调用同一个 `Backtest.run` 即可，行情准备可复用，每次账户独立。不要复用带有未重置内部状态的策略对象。参数优化器、并行搜索和滚动验证尚未内置。

完整可运行案例见[研究与报告示例](reports.md)。
