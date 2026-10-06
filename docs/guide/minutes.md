# 分钟回测

分钟策略沿用 `Backtest` 和 `Context`，输入改为 `MarketData.from_minutes`，周期为 `1min` 或 `5min`。

## 准备分钟行情

```{literalinclude} ../../examples/minute.py
:language: python
:pyobject: sample
```

`MinuteClock.build(days, "1min")` 生成 09:31–11:30、13:01–15:00 的 bar 结束时点，每日 240 根；5 分钟为每日 48 根。它只为传入的日期生成网格，不识别交易所节假日。

示例全部声明为 `continuous`，用于演示连续交易。真实数据须按实际区间标记 `continuous`／`auction`；竞价区间只估值、不模拟成交。所有时间必须带 `+08:00` 时区。详见[分钟数据契约](../minute-execution.md)。

## 部分成交与 T+1

```{literalinclude} ../../examples/minute.py
:language: python
:pyobject: strategy
```

首日第一根 bar 收盘后买入 1000 份，次日第一根 bar 收盘后卖出。配置 10% 参与率、每根成交量 1000 时，每根最多成交 100 份，需要多次完成订单。两边订单各自累计计算最低佣金，成交一次不会重复收费 5 元。

```sh
python examples/minute.py
python examples/minute.py --backend numba
python examples/minute.py --backend numba --precomputed
```

后两条命令需安装 Numba。完整{download}`分钟示例 <../../examples/minute.py>`采用相同的两日人工行情。

## 配置滑点与参与率

```python
from doribt import BarExecution, Costs, FixedBps, RunConfig

config = RunConfig(
    initial_cash=100_000,
    costs=Costs(commission=0.0003, minimum_commission=5),
    execution=BarExecution(participation=0.1, slippage=FixedBps(5), slippage_policy="cost"),
)
```

5 bps 为单边 0.05%。也可使用 `FixedTicks(1)` 或 `VolumeImpact(coefficient=0.1)`。上例选择 `cost`：完整计入滑点，允许模拟结算价超过 bar 高低价或当日涨跌停价。省略 `slippage_policy` 时默认 `strict`，越界不成交；`cap` 则截到边界，会削减滑点成本。

三种模式都保留原始行情的成交资格、T+1、量限与资金约束，以及用户对最终结算价设置的 `limit_price`。涨停买入、跌停卖出的原始开盘阻断仍然有效，详见[滑点边界契约](../minute-execution.md#费用滑点与失败)。

完整{download}`滑点比较示例 <../../examples/slippage.py>`在三日平价人工行情上演示高点买入、低点卖出：

```sh
python examples/slippage.py
```

零手续费、100 份、单边 0.02 元滑点：`strict` 没有成交，`cap` 买卖都按 10 元结算，`cost` 买入 10.02 元、卖出 9.98 元，往返滑点成本为 4 元。`Fill.reference_price` 保留 10 元参考价，`Fill.slippage_cost` 可用于解释成本；它已计入现金与收益，不要重复扣减。

`next_bar` 只尝试下一根；`day` 持续到首个可执行 bar 所属交易日结束，午休不撤单。T+1 按交易日推进，不能在同一天买入后再卖出未解锁股份。

执行使用下一根 bar 的开盘价及最终成交量，是 bar 级模拟。成交在该 bar 结束时可见，不表示开盘时已知全部成交量。日频研究指标请用 `result.report()`，不要把每分钟收益直接按 252 年化。
