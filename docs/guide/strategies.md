# 编写策略

策略是接收 `Context` 的普通函数，每根 bar 完成后调用一次。通过历史窗口读取数据，通过账户快照观察持仓，通过下单方法表达意图。

## 均线择时

```{literalinclude} ../../examples/strategies.py
:language: python
:pyobject: moving_average
```

历史窗口包含当前已完成 bar；样本不足时返回已有数据，所以先判断长度。目标在下一根 bar 才尝试执行，最后一根 bar 产生的信号不会在样本外成交。

完整脚本和人工数据在{download}`strategies.py <../../examples/strategies.py>`。运行 `python examples/strategies.py`，依次比较买入持有、均线择时和双证券轮动。

## 选择下单方式

| 方法 | 含义 | 适用任务 |
| --- | --- | --- |
| `ctx.order("DEMO", 1000, valid_for="day")` | 买入固定 1000 份；负数卖出 | 控制单笔订单和有效期 |
| `ctx.target_positions({"DEMO": 1000})` | 持续尝试达到 1000 份 | 明确持仓数量 |
| `ctx.target_weights({"DEMO": 0.8})` | 按当前收盘权益计算目标股数 | 择时或资产配置 |

固定订单返回订单 ID，用 `cancel_order` 撤单；持仓目标返回意图 ID，用 `cancel` 取消。两种 ID 不混用。

`target_positions` 中省略的证券保持原目标；`target_weights` 描述整个组合，省略的证券目标为零。权重总和不得超过 1。

## 组合轮动

```{literalinclude} ../../examples/strategies.py
:language: python
:pyobject: rotation
```

这个日线示例每五个输入交易日重新选择动量更高的证券。`rebalance=True` 按最新权益重新计算股数。实际成交受可卖量、资金、费用与成交量约束，不能保证精确达到目标权重。

多个证券共享一个账户。先卖后买，买入顺序按 `MarketData.symbols` 的声明顺序，现金不足时排序会影响结果。多组参数应各自调用 `run`，不会共用资金。

## 预计算信号

已有目标数组时，使用 `WeightTargets(sessions=data.timeline, weights=...)` 或 `PositionTargets(..., quantities=...)`。数组必须与完整时间轴精确对齐，不能省略、排序或前填。

```{literalinclude} ../../examples/sma.py
:language: python
:pyobject: sma_hold
```

{download}`完整预计算示例 <../../examples/sma.py>`只使用截至当时的窗口。引擎会延后执行，但不会自动证明外部指标没有未来数据。其执行路径与性能边界见[预计算目标](../scheduled-execution.md)。
