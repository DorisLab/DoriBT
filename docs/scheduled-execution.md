# 预计算目标的执行优化

预计算目标减少 Python 调度，保持同一套订单、成交、权益和结果接口。满足明确条件的日线股数目标使用编译循环，其余预计算输入继续使用事件分段调度。

## 使用方式

```python
from doribt import Backtest, PositionTargets, RunConfig

# quantities 为在每个收盘时点已知的目标股数，长度必须与 data.timeline 一致。
targets = PositionTargets(sessions=data.timeline, quantities={symbol: quantities})
result = Backtest(data, config=RunConfig(backend="numba")).run(targets)
```

完整人工数据示例：`uv run --no-sync python examples/minute.py --precomputed --backend numba`。基础安装可用 `backend="python"`；缺少 Numba 时指定 Numba 会明确报错。

`PositionTargets` 首个时点声明所列证券的目标，此后仅在某证券数值变化时替换该证券的意图；未列证券保持不变。相同数值不会每分钟取消重下，不会反复调仓，也不会覆盖公司行动已对未完成意图作出的股数调整。需要主动重新声明同一目标或依据成交改变决策时，使用普通 Context 回调。目标股数是非负整数，输入会复制并冻结；时间与行情必须完全对齐。预计算不会替使用者消除因子中的未来信息。

`WeightTargets` 在 BarExecution 下也使用分段路径；`sizing="close"` 默认按决策收盘定量，`sizing="execution"` 在下一 bar 开盘定量一次。`rebalance=False` 保留确定后的股数目标，`rebalance=True` 逐 bar 发出重新定量的意图，因此通常不能跳过区间。模式、权重、日期和重算选项都进入来源指纹。任意回调和预计算类的自定义子类仍逐 bar 调用，不能因为对象继承了目标类就省略用户逻辑。

## 日线股数目标的编译循环

使用 Numba、精确内置 `PositionTargets`、日线数据及 `BarExecution`，且行情没有任何公司行动时，引擎将完整的每日目标推进、子单申报、冻结、撮合、交收、日末税务批次和估值放入一个编译循环。无需启用额外选项；不同目标规模、任意受支持的费用、数量规则、交收延迟、成交量参与率和三种滑点仍按原契约处理，不假定资金充足或交易完全成交。

数值数组保存账户和完整审计状态，执行结束后一次物化现有不可变 Order、Fill、IntentRecord 与 TaxLotRecord；不会丢弃拒单、部分成交、意图替换或已消耗批次的编号。申报仍使用前一收盘时点的规则和价格，按意图插入顺序冻结资金，撮合仍先卖后买。未完成买单的剩余冻结资金到日末才释放，T+N 可卖量与税务 FIFO 分开维护。

公司行动、分钟数据、WeightTargets、自定义目标子类和任意回调均保留现有路径；基础 Python 后端也保持分段实现。不是整个引擎或所有策略都被编译。首次 JIT 编译和数组准备需要额外时间与内存，暖态速度不能代表冷启动；极大输入还需为数值审计缓冲区预留内存。

## 为什么按事件分段

分段调度复用 Broker／Account／RightsBook，仅减少状态未变化区间的重复工作；逐笔成交与权益生命周期仍按统一规则处理。

- 目标变化、可能成交、交易日首尾和需要生成／完成意图的 bar，继续走现有生命周期。
- 同一交易日内，没有策略变化且订单资源稳定时，扫描到下一次可能成交。Numba 编译整个扫描循环；一旦发现可能成交，立即交回 Broker 处理先卖后买、共享资金、交收和一单多次费用。
- 预计算目标每证券最多一个活动子单；无成交区间内资金、持仓、可卖量和量限占用不变。扫描不修改账户，不假定不同证券资金独立。
- 无成交区间批量计算逐 bar 原始价估值，保留现金、持仓、可卖量、冻结、待入账股份和税务快照；最后一个未成交 bar 仍更新订单原因与时间。估值保持溢出与缺价拒绝。
- 交易日首尾始终处理，所以分红、送转、T+N 解锁、每日税务和 DAY 到期不会被跳过。不同日的规则变化也不会跨越。

以上是未进入日线编译循环时的事件分段调度，**不是整个回测引擎都进入 Numba**。实际成交密集、每分钟改变目标或 Python 回调计算密集时，收益会减少；不提供参数并行器，不删减结果字段。

## 可观察性与缓存

`result.run_info.to_dict()["execution_path"]` 区分 `scheduled_segments` 与 `bar_callbacks`。为保持来源格式兼容，`scheduled_segments` 表示预计算执行族，也包含上述日线编译循环，不是内部内核选择标志。PositionTargets 保存目标输入及哈希；子类按回调记录代码来源，避免把自定义行为误说成已被目标数组完整捕获。

同一 Backtest 缓存不可变 MarketData 的准备结果和来源 JSON，目标对象缓存自身来源 JSON；生成完整 RunInfo 时仍重新记录费用、策略参数、依赖版本和源码哈希。替换数据会重建对应缓存，账户和订单始终新建。输出仍为同样的规范 JSON，既不省略大样本的时间戳，也不把序列化推迟到 benchmark 之外。

## 验证与边界

以同一预计算对象的普通回调包装作为逐 bar 对照，核对所有结果数组、意图、订单、成交、冻结、公司行动和税务记录；独立 Decimal 参考另行验证真实分钟案例。覆盖多证券资金不足、目标替换、数量上限、零股余量、T+0／T+1／T+2、三种滑点、竞价、停牌、分红送转和最终未执行意图。

性能以完整 Backtest API 和结果物化计时，逐 bar 回调、预计算 Python、预计算 Numba 及 vectorbt 用同一数据与目标。数据准备、预计算对象构造和对账另计；包括冷调用、新 JIT 缓存、预热单账户、十组参数和进程树内存。测量及限制见[优化后的分钟比较](https://github.com/DorisLab/DoriBT/blob/main/engineering/history/minute-performance-optimized.md)。
