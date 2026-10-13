---
myst:
  html_meta:
    description: "用 DoriBT 编写多 ETF 动量轮动策略，理解共享账户、历史窗口与再平衡，比较费用和基准并导出可核对的研究报告。"
---

# A 股 ETF 轮动回测：动量、共享资金与再平衡

**目标**：在共享现金账户里，每五个交易日比较两只 ETF 的动量，持有较强的一只，并检查换仓、费用与基准。

完成后，你会得到一份可重复运行的策略脚本和 `etf-rotation-report/` 报告目录。先用人工行情验证研究流程，再接入有授权的真实行情；本例结果不说明策略有投资价值。

## 1. 准备可重复的数据

先按[安装指南](../guide/install.md)安装 DoriBT。下载{download}`strategies.py <../../examples/strategies.py>`，把下文代码依次保存到同一目录的 `tutorial_etf_rotation.py`。不要把自己的脚本命名为 `doribt.py` 或 `strategies.py`。

这里复用示例的 `synthetic_market()`。它创建 ALPHA、BETA 两只人工 ETF、固定价格路径和共享日历，无需网络、账户或随机种子。日期仅筛去周末，**没有处理真实交易所节假日**；自定义规则是人工 T+1、100 份申报单位、零印花税和过户费，不能直接作为真实证券配置。

```python
from pathlib import Path

from strategies import synthetic_market

from doribt import Backtest, Benchmark, Context, Costs, Parameter, ParameterSet, RunConfig

data = synthetic_market()
print("证券顺序：", data.symbols)
print("交易日数：", len(data.sessions))
```

运行数据先有两个检查点：证券顺序为 `ALPHA, BETA`，共有 86 个输入交易日。证券顺序也决定同动量时的优先级及资金不足时的买入顺序，研究时应固定它。

## 2. 把研究问题写成策略

本例提前固定这些选择：

- 观察最近 20 根已完成日线，用末价／首价减一计算动量。这是 20 个价格点、19 个收益间隔
- 每五个输入交易日决策一次，不等同于自然周周五
- 选择动量最高的证券，目标权重 95%，其余持仓清零；即使两者动量都为负，也仍选择较强者
- 留出 5% 现金缓冲，费用与整手限制仍可能使实际仓位偏离目标
- 按决策收盘权益定量，下一根 bar 开盘才尝试成交

```python
parameters = ParameterSet(
    {
        "lookback": Parameter(type="int", default=20, minimum=2, maximum=60),
        "every": Parameter(type="int", default=5, minimum=1, maximum=20),
        "allocation": Parameter(type="float", default=0.95, minimum=0, maximum=1),
    }
)


def rotation(ctx: Context, *, lookback: int, every: int, allocation: float) -> None:
    completed = ctx.bar_index + 1
    if completed < lookback or completed % every:
        return
    momentum = {}
    for symbol in ctx.symbols:
        history = ctx.history(symbol, bars=lookback)
        momentum[symbol] = float(history[-1] / history[0] - 1)
    winner = max(momentum, key=lambda symbol: momentum[symbol])
    ctx.record(
        momentum_alpha=momentum["ALPHA"],
        momentum_beta=momentum["BETA"],
        selected_index=ctx.symbols.index(winner),
    )
    ctx.target_weights({winner: allocation}, rebalance=True)


def hold_alpha(ctx: Context) -> None:
    ctx.target_weights({"ALPHA": 0.95})
```

`ctx.history` 只含当前及之前已完成的 bar。`target_weights` 表示整个组合，省略的证券目标为零；`rebalance=True` 表示每次决策按最新权益重新定量，即使获胜证券没有变化。日常追加一个证券而不动其他持仓时，不能把这个语义当成 `target_positions` 的语义。

`ctx.record` 留下每次决策的动量和选中证券序号，便于解释换仓。非决策日为空，不自动前填。`selected_index=0` 对应 ALPHA，`1` 对应 BETA。

## 3. 用相同费用比较轮动和持有

```python
config = RunConfig(
    initial_cash=100_000,
    costs=Costs(commission=0.0003, minimum_commission=5),
    backend="python",
)
result = Backtest(data, config=config).run(rotation, parameter_schema=parameters)
hold_result = Backtest(data, config=config).run(hold_alpha)

# 价格基准不模拟费用；另跑的 hold_result 才是有相同费用约束的对照账户。
benchmark = Benchmark(
    sessions=data.sessions,
    prices=data.prices("close")[:, 0],
    name="ALPHA 人工价格基准",
    source=data.source,
)
report = result.report(benchmark=benchmark, periods_per_year=252)
print("轮动期末权益：", round(float(result.equity[-1]), 2))
print("持有期末权益：", round(float(hold_result.equity[-1]), 2))
for name in ("total_return", "max_drawdown", "total_fees", "turnover", "excess_total_return"):
    print(name, report.stats[name])
print("实际参数：", result.run_info.to_dict()["parameters"])
```

两个 `run` 各有独立账户，不能把参数实验当作一个共享资金组合。轮动账户内的 ALPHA 与 BETA 才共享 100000 元；换仓先卖后买，但 T+1、停牌、量限和资金不足都可能阻止目标达成。

此处没有额外配置滑点，使用默认成交模型；不是“无摩擦”的证据。正式研究应另做佣金、最低佣金、滑点及成交量参与率的敏感性比较，见[分钟与成交成本配置](../guide/minutes.md)。年化显式采用 252 个交易日，不能从这份人工工作日日历推断真实年化结果。

按本页参数，轮动期末权益应为 **90046.55 元**，持有 ALPHA 的对照账户为 **116025.76 元**。轮动在这份固定人工样本中亏损；这个结果用于确认代码一致，不应通过反复改参数把它“修成”盈利。

## 4. 检查成交，再保存结果

```python
for fill in result.fills[:6]:
    print(fill.session, fill.symbol, fill.quantity, fill.price, fill.fees)

blocked = [order for order in result.orders if order.reason.value != "none"]
print("带约束原因的订单：", len(blocked))
for order in blocked[:5]:
    print(order.session, order.symbol, order.filled, order.reason.value)

assert result.symbols == ("ALPHA", "BETA")
assert len(result.fills) > 0
output = result.export(Path("etf-rotation-report"), benchmark=benchmark, daily=True)
print("报告目录：", output)
```

在脚本所在目录运行：

```sh
python tutorial_etf_rotation.py
```

报告目标目录必须尚不存在，重复实验请改用一个新目录名，不会覆盖旧研究。先读 `fills.csv` 的换仓方向、`orders.csv` 的受阻原因，再读 `report.json` 的收益和回撤；`research.json` 保留刚才的动量记录，`run.json` 保留实际参数与数据来源。详细文件含义见[结果与导出](../results.md)。

要导出图表，安装 `doribt[plot]`，并在本次 `export` 调用中加 `plot=True`；这会在同一个新报告目录生成 `equity.png`。

## 5. 换成真实 ETF 时改哪里

本例的轮动逻辑假定两只证券在整个回测区间始终上市，且每个决策窗口都有完整、有限的价格。对这样的证券池，可保留策略与分析部分，替换 `data = synthetic_market()`。用[数据到报告教程](data-to-report.md)中的 `MarketData.from_csv` 或 `from_records` 接入已取得授权的原始行情，同时提供：

1. 独立交易所日历，包含没有成交的交易日；不要从现有价格行反推日历
2. 每日、每个证券恰好一行，停牌、上市前及退市后状态明确
3. 证券身份、经核验的 `china_rules` profile 或自定义日期规则，以及每日真实涨跌停价
4. 期间完整公司行动；需要连续研究价时提供可知时点正确的复权因子，并把历史读取改为 `adjustment="asof"`

若研究池包含新上市或退市证券，历史窗口可能含 NaN；不能把它们直接交给 `max` 排名。应先加入基于当时已知信息的资格筛选，并明确没有合格标的时是目标清零还是维持仓位，再验证上市前、退市后和窗口不足的分支。行情行仍须完整，不能靠删行绕过输入契约。停牌证券是否参与排名也应由研究问题明确，实际成交仍受状态约束。

真实代码可以替换 ALPHA、BETA；也要同步改掉 `ctx.record` 中的两处人工名称。扩展到更多证券时，考虑把每只证券的动量记录命名规则写成一个明确的数据映射。

常见误区：

- 用同一根 bar 的收盘选出赢家，却认为已经按该收盘成交：本例最早下一根开盘执行
- 用截止今天的前复权序列计算所有历史信号：可能带入当时未知的事件信息
- 从当前上市 ETF 列表选回测池：可能遗漏退市或合并标的，产生幸存者偏差
- 用样本内最好参数作结论：先固定比较指标、训练／检验区间，再另跑独立样本；参数声明本身不是优化器
- 把价格基准当作扣费的可交易持有策略：两者口径不同，上面已经分别运行

下一步读[策略与目标语义](../guide/strategies.md)、[原始价与研究复权](../data-contract.md)和[市场支持矩阵](../china-market.md)。
