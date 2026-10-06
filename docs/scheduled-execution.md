# 预计算目标的分段执行

状态：0.2.0.dev0 本地开发版，尚未发布。目标是减少分钟数据上的 Python 调度开销，保持同一套订单、成交、权益和结果接口。

## 使用方式

```python
from doribt import Backtest, BarExecution, PositionTargets

# quantities 为在每个收盘时点已知的目标股数，长度必须与 data.timeline 一致。
targets = PositionTargets(sessions=data.timeline, quantities={symbol: quantities})
result = Backtest(data, execution=BarExecution()).run(targets, backend="numba")
```

完整人工数据示例：`uv run --no-sync python examples/minute.py --precomputed --backend numba`。基础安装可用 `backend="python"`；缺少 Numba 时指定 Numba 会明确报错。

`PositionTargets` 首个时点声明所列证券的目标，此后仅在某证券数值变化时替换该证券的意图；未列证券保持不变。相同数值不会每分钟取消重下，不会反复调仓，也不会覆盖公司行动已对未完成意图作出的股数调整。需要主动重新声明同一目标或依据成交改变决策时，使用普通 Context 回调。目标股数是非负整数，输入会复制并冻结；时间与行情必须完全对齐。预计算不会替使用者消除因子中的未来信息。

已有 `WeightTargets` 在 BarExecution 下也使用分段路径；`rebalance=False` 仍保留固定股数目标，`rebalance=True` 仍逐 bar 重新分配，因此通常不能跳过区间。日线原有执行模型保留原路径。任意回调和预计算类的自定义子类仍逐 bar 调用，不能因为对象继承了目标类就省略用户逻辑。

## 为什么按事件分段

首轮 profile 显示主要开销来自逐 bar 创建 Context、持仓视图、账户数量数组及权益快照，单独编译成交函数没有显著改善总耗时。直接另写完整数组账本会形成两套需要长期维护的订单、税务和公司行动实现。本轮保留正式 Broker／Account／RightsBook，仅减少状态未变化区间的重复调度。

- 目标变化、可能成交、交易日首尾和需要生成／完成意图的 bar，继续走现有生命周期。
- 同一交易日内，没有策略变化且订单资源稳定时，扫描到下一次可能成交。Numba 编译整个扫描循环；一旦发现可能成交，立即交回 Broker 处理先卖后买、共享资金、交收和一单多次费用。
- 预计算目标每证券最多一个活动子单；无成交区间内资金、持仓、可卖量和量限占用不变。扫描不修改账户，不假定不同证券资金独立。
- 无成交区间批量计算逐 bar 原始价估值，保留现金、持仓、可卖量、冻结、待入账股份和税务快照；最后一个未成交 bar 仍更新订单原因与时间。估值保持溢出与缺价拒绝。
- 交易日首尾始终处理，所以分红、送转、T+N 解锁、每日税务和 DAY 到期不会被跳过。不同日的规则变化也不会跨越。

这是预计算策略的事件分段调度，**不是整个回测引擎都进入 Numba**。实际成交密集、每分钟改变目标或 Python 回调计算密集时，收益会减少；本轮没有新增参数并行器或删减结果字段。

## 可观察性与缓存

`result.run_info.to_dict()["execution_path"]` 区分 `scheduled_segments` 与 `bar_callbacks`。PositionTargets 保存目标输入及哈希；子类按回调记录代码来源，避免把自定义行为误说成已被目标数组完整捕获。

同一 Backtest 缓存不可变 MarketData 的准备结果和来源 JSON，目标对象缓存自身来源 JSON；生成完整 RunInfo 时仍重新记录费用、策略参数、依赖版本和源码哈希。替换数据会重建对应缓存，账户和订单始终新建。输出仍为同样的规范 JSON，既不省略大样本的时间戳，也不把序列化推迟到 benchmark 之外。

## 验证与边界

以同一预计算对象的普通回调包装作为逐 bar 对照，核对所有结果数组、意图、订单、成交、冻结、公司行动和税务记录；独立 Decimal 参考另行验证真实分钟案例。覆盖多证券资金不足、目标替换、数量上限、零股余量、T+0／T+1／T+2、三种滑点、竞价、停牌、分红送转和最终未执行意图。

性能以完整 Backtest API 和结果物化计时，旧回调、预计算 Python、预计算 Numba 及 vectorbt 用同一数据与目标。数据准备、预计算对象构造和对账另计；包括冷调用、新 JIT 缓存、预热单账户、十组参数和进程树内存。测量及限制见[优化后的分钟比较](minute-performance-optimized.md)。
