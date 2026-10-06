# 分钟行情、部分成交与滑点

使用 `RunConfig` 时，日线和分钟均由 `BarExecution` 控制成交量、滑点和订单有效期。本页定义 bar 级模拟的完整行为。

## 数据与时间

`MarketData.from_minutes(records, calendar=..., frequency="1min", ...)` 接收原始 OHLC、股数单位成交量、明确涨跌停价和交易状态。每行额外提供带 +08:00 的区间结束 `timestamp` 和 `phase`（continuous / auction）。支持 1min、5min；一轮回测只能一种频率。完整交易日网格为上午 09:30–11:30、下午 13:00–15:00，缺行报错，停牌必须显式给零量估值。午休不生成行；集合竞价保留估值但不模拟成交，跨越竞价边界的区间须标记 auction。日历由提供方保证是实际交易日。

交易日与分钟位置分离。`ctx.session` 是交易日，`ctx.now` 是已完成 bar 的时间，`ctx.bar_index` 是 bar 序号。T+N 按提供的交易日推进；公司行动开盘处理一次、股息税与登记权益日终处理一次。历史只包含已完成 bar；分钟复权的因子可知日期沿用日级声明。

完成 bar 后提交订单，最早下一 bar 执行。参考下一 bar 开盘价、加入不利滑点，用该 bar 最终成交量限制参与率；成交记录时间为该 bar 结束，不能声称开盘时已知成交量。此模型是 bar 级模拟，不推断撮合队列或盘口。

## 订单与账户

`ctx.order(symbol, quantity, valid_for="next_bar" | "day", limit_price=None)` 返回订单 ID；`ctx.cancel_order(id)` 撤销剩余量。同标的允许多单，共用本 bar 成交容量，先卖后买、同方向按提交顺序。买卖的申报数量先按板块检查；部分成交按单股记录，不将余量误当成新申报再按整手拒绝。

DAY 的有效期为首个可执行 bar 所属交易日，午休保留、该日结束到期；next_bar 在下一 bar 尝试一次后到期。最后一根 bar 提交的订单保留未执行记录。一个订单可以多次成交，订单记录汇总成交金额/费用和状态，Fill 保留逐笔价格/时间；最低佣金按同一订单的累计成交金额算增量。印花税和过户费按每笔成交计算并取分。

直接股数单返回 order_id，撤销使用 `cancel_order`；持仓／权重目标返回 intent_id，撤销继续使用 `cancel`。两种 ID 不能混用。`ctx.orders`／`ctx.intents` 应在当前回调内查询并保留返回的不可变记录；不查询时不构造整份历史。`result.orders` 的 `price` 是累计成交均价，逐笔精确价格以 `result.fills` 为准。

跨日后余量是新子单，仍须遵守申报规则：可买数量向合法步长下取整；不足最小申报量的残差保留为未满足目标，不暗中超买。卖出整仓可以按规则清理零股。bar 成交金额保留万分之一元精度（小份额 ETF 部分成交可能产生不足分的金额），费用按分舍入。

挂单占用现金预算或可卖股数，撤单/到期/成交释放。买入市场单按提交时已知价格和滑点估算预算，最多占用当时可用现金；跳空后只可在该预算内成交，不能挪用其他订单的冻结资金。限价买单按限价预留。资金不足允许部分成交，未成交量继续受有效期约束。卖单不得超卖；T+1 的未解锁股份不能冻结为可卖股份。目标持仓跨日保留，每日生成子单并在日内延续，替换目标撤销旧子单。日终子单到期不等于放弃目标。直接股数单与目标子单共享资源和成交量。

## 费用、滑点与失败

`Costs` 管理费用；`BarExecution(participation=.05, slippage=FixedBps(5))` 管理容量和滑点，另外支持 FixedTicks、VolumeImpact。滑点先按买入加价、卖出减价计算，并向不利方向对齐 tick。成交量冲击使用本 bar 已使用量加本次拟成交量的参与率平方，系数是调用者的研究假设。

`slippage_policy` 决定滑点后的价格如何处理，适用于上述三种模型：

| 取值 | 越过 bar 高低价或当日涨跌停价时 | 适用假设 |
| --- | --- | --- |
| `strict`（默认） | 本次不成交，记录 `price_out_of_range` | 要求模拟成交价处于历史价格范围内 |
| `cap` | 将价格截到 bar 区间与当日涨跌停区间的交集 | 接受滑点被边界削减，不保证扣足设定成本 |
| `cost` | 保留完整滑点，允许模拟结算价越界 | 将滑点视为研究成本，避免仅因越界取消交易 |

例如开盘价与最高价都是 10 元，买入滑点 0.02 元：`strict` 不成交，`cap` 以 10 元结算，`cost` 以 10.02 元结算。最低价卖出同理；日涨跌停边界也使用同一策略。

三种策略都先按原始开盘价和行情状态判断成交资格。停牌、无量、竞价，以及开盘已在涨停价时买入／跌停价时卖出的阻断不变；也不放宽 T+1、持仓、共享量限和资金约束。`cost` 允许的是**滑点后的模拟结算价**越界，不能据此推断涨停可以买到或跌停可以卖出。

显式 `limit_price` 仍保护最终结算价，超过限价返回 `limit_price`，不会为满足用户限价自动截价。结算价必须为正。买入可负担数量、成交金额及按金额计算的税费均使用最终结算价，因此增加成本仍可能因资金不足减少数量。挂单冻结预算用提交时已知价格及完整滑点估算，不读取未来 bar 的边界；`cap` 在实际执行时用截价后的价格计算可买量。

`Fill.reference_price` 记录滑点前的开盘参考价，`Fill.price` 是最终模拟结算价；两者的差额乘有符号成交数量得到 `Fill.slippage_cost`。该成本已经计入成交金额，不是单独收取的手续费，不能再次从现金扣除。`run_info` 和导出记录保留边界策略与参考价，详见[结果契约](results.md)。

滑点通过 `BarExecution.slippage` 配置，不能同时设置非零 `Costs.slippage_ticks`。冲击系数由调用者指定，不静默推断真实冲击或卖出可用量。

当前限价是成交价格保护，参考价仍是下一 bar 开盘加滑点；不模拟盘中触价、队列优先或竞价撤单规则。冻结字段记录完成 bar、策略回调前的状态；回调内连续提交仍由 broker 的即时余额控制。`stats()` 保留输入 bar 口径且不默认年化；`report()` 按日末采样，默认每年 252 个交易日。

```python
from doribt import Backtest, BarExecution, FixedBps, RunConfig

# data 为调用者已准备的 MarketData；完整示例见下文。


def strategy(ctx):
    if ctx.bar_index == 0:
        ctx.order("DEMO", 1000, valid_for="day")


result = Backtest(
    data,
    config=RunConfig(execution=BarExecution(participation=0.05, slippage=FixedBps(5))),
).run(strategy)
print(result.stats())
```

预计算目标使用 `WeightTargets(sessions=data.timeline, weights=...)`。`data.sessions` 保留唯一交易日；`data.timeline` 是 bar 结束时点。分钟 `prices(as_of=...)` 必须传带时区的具体结束时点。

完整可运行脚本见[分钟教程](guide/minutes.md)，预计算优化与边界见[分段执行](scheduled-execution.md)。
