---
myst:
  html_meta:
    description: "用人工 1／5 分钟行情研究 ETF 做 T，比较 T+0、T+1 与昨日底仓，解释可卖量、成交滑点、未成交原因及日频报告。"
---

# 分钟做 T

**目标**：区分“信号想卖”“账户有持仓”和“当前可以卖”，验证 T+0、T+1 与昨日底仓三种研究假设的实际成交。

完成后，你会得到四个情景的成交对照、可以手工核对的现金账本，以及 `intraday-t-report/` 分钟报告。两日人工价格让每笔成交和费用都能直接手算。

## 1. 先运行现成实验

按[安装指南](../guide/install.md)安装后，下载{download}`intraday_t.py <../../examples/intraday_t.py>`。在该文件所在目录运行：

```sh
python intraday_t.py
python intraday_t.py --frequency 5min
```

两种频率都用完整分钟网格，信号出现在第二日开头。1 分钟每日 240 根，5 分钟每日 48 根。示例 bar 全部为连续交易；接入真实行情时，以 `auction` 标记竞价区间。

四个模式的区别：

| 模式 | 市场／账户假设 | 用途 |
| --- | --- | --- |
| `t0` | 股票型 ETF 只在第二日用 `RuleOverride` 改为 T+0 | 与 T+1 对照，观察可卖延迟对交易的影响 |
| `t1` | 股票型 ETF 的 T+1 预设，无昨日持仓 | 验证当天买入后无法卖出 |
| `inventory` | T+1，首日先买 1000 份底仓 | 次日先卖后买，检查底仓是否耗尽 |
| `native` | 黄金 ETF 的原生 T+0 profile | 在对应市场分类假设下执行同日往返 |

`DEMO` 是人工标识。接入自己的证券时，选择对应的市场分类，行情提供每日价格边界，详见[市场规则](../china-market.md)。

## 2. 理解时间顺序与底仓

示例策略读取刚完成 bar 的收盘价：低于 10 元时买入 1000 份，高于 10 元时尝试卖出 1000 份。订单最早在下一根 bar 开盘撮合，成交到该 bar 结束才可见。

```{literalinclude} ../../examples/intraday_t.py
:language: python
:pyobject: round_trips
```

没有昨日底仓时，第二天新买入的 1000 份要到下一交易日才可卖。`ctx.account.positions["DEMO"].quantity` 是持仓；应同时检查该持仓的 `sellable`。这里故意只判断持仓、再尝试卖出，用订单结果展示真实约束。

底仓版本首日先买入，次日的高价信号卖出昨日股份，低价信号再买回：

```{literalinclude} ../../examples/intraday_t.py
:language: python
:pyobject: inventory_t
```

买回的份额形成新的 T+1 批次：总持仓回到 1000，可卖量仍为 0，要到下一交易日才解锁。规则覆盖按买入成交日决定批次可卖日，不会追溯把旧批次改成当天可卖。

## 3. 自己运行、核对四个情景

把以下代码依次保存为 `tutorial_intraday_t.py`，与下载的 `intraday_t.py` 放在同一目录。这里使用它的公开示例函数生成固定行情；账户与分析仍通过 DoriBT 顶层 API 调用。

```python
from pathlib import Path

import numpy as np
from intraday_t import inventory_t, round_trips, sample

from doribt import Backtest, BarExecution, Costs, FixedTicks, RunConfig

config = RunConfig(
    initial_cash=100_000,
    costs=Costs(commission=".0003", minimum_commission=1),
    execution=BarExecution(participation=".1", slippage=FixedTicks(1)),
    backend="python",
)
expected = {
    "t0": ([1000, -1000, 1000, -1000], 100383.88),
    "t1": ([1000], 99996.00),
    "inventory": ([1000, -1000, 1000], 100187.94),
    "native": ([1000, -1000, 1000, -1000], 100383.88),
}
results = {}
for mode, (quantities, final_equity) in expected.items():
    strategy = inventory_t if mode == "inventory" else round_trips
    result = Backtest(sample(mode, "1min"), config=config).run(strategy)
    results[mode] = result
    assert [fill.quantity for fill in result.fills] == quantities
    assert int(result.equity_units[-1]) == round(final_equity * 10_000)
    print(mode, quantities, "期末权益", f"{result.equity[-1]:.2f}")
    print("期末持仓／可卖：", result.holdings[-1, 0], result.sellable[-1, 0])
```

配置中的一档滑点按当期规则价位计算。在这里 ETF 的一档为 **0.001 元**，买入价 10.001、卖出价 10.199。不要把股票常见的 0.01 元档位套过来。每根成交量 50000 份、参与率 10%，单根上限 5000 份，因此这里的 1000 份订单可以一次成交。

1 分钟 `t0` 的四笔成交依次在第二日 09:32、09:33、09:34、09:35；5 分钟模式相应为 09:40、09:45、09:50、09:55。T+1 底仓模式的第一笔买入在首日，不能把它当成第二日凭空出现的初始持仓。

手算 `t0`：每次往返毛价差为 `1000 × (10.199 − 10.001) = 198` 元，买卖佣金合计 6.06 元，两次净增 `2 × (198 − 6.06) = 383.88` 元。滑点已进入成交价，不要把滑点成本再扣一次。

## 4. 把未成交也当作研究结果

```python
inventory_result = results["inventory"]
for order in inventory_result.orders:
    if order.reason.value != "none":
        print("未完成约束：", order.session, order.quantity, order.filled, order.reason.value)
assert any(order.reason.value == "insufficient_sellable" for order in inventory_result.orders)
assert inventory_result.holdings[-1, 0] == 1000
assert inventory_result.sellable[-1, 0] == 0

# 本例无公司行动：逐根权益应等于现金加原始收盘价下的持仓价值。
reconstructed = inventory_result.cash_units + np.sum(
    inventory_result.holdings * inventory_result.close_units, axis=1
)
np.testing.assert_array_equal(reconstructed, inventory_result.equity_units)

for fill in inventory_result.fills:
    print(fill.timestamp, fill.quantity, fill.reference_price, fill.price, fill.fees)
```

`insufficient_sellable` 是本例预期，而不是引擎漏卖。真实策略可以先检查 `sellable` 再提交订单，减少无效申请；审计时仍应保留原始信号和受约束的成交结果。

上面的简化权益恒等式只适用于这份没有公司行动的输入。有应收分红、待入账股份或税款时，还需把这些项目纳入对账，见[结果字段](../results.md)和[公司行动](../corporate-actions.md)。

## 5. 日频汇总，保留分钟审计

```python
daily_report = inventory_result.report(periods_per_year=252)
assert len(daily_report.daily) == 2
print("日数：", len(daily_report.daily))
print("总收益率：", daily_report.stats["total_return"])
output = inventory_result.export(Path("intraday-t-report"), daily=True)
print("报告目录：", output)
```

```sh
python tutorial_intraday_t.py
```

`report.json` 按日末采样，`account.csv`、`positions.csv` 和逐笔成交仍保留完整分钟记录。已定义的统计值直接展示；样本不足的指标返回 `None`。重新运行时要换一个尚不存在的报告目录名。

如果已经安装 `doribt[numba]`，可以把配置改为 `backend="numba"`；也可以用下载脚本的 `--backend numba` 参数核对同一人工案例。预热后重复运行可复用编译缓存。

## 6. 接真实分钟数据前的检查表

- 时间为带 `+08:00` 的 bar 结束时点，`frequency` 与输入一致；独立日历加完整网格用于发现漏分钟
- `continuous`／`auction` 按实际时段标记；竞价与盘后撮合不在本例模型内
- OHLC 为未复权人民币价格，成交量为股／份；不能直接把供应商的“手”当“份”
- 信号只用当时已完成信息；不因回测提供了下一 bar 成交量而在前一 bar 决策时使用它
- 参与率、最低佣金、滑点与订单有效期明确。`next_bar` 只尝试下一根，`day` 才延续到首个可执行 bar 所属交易日结束
- T+1 按交易日推进；真实证券按当期市场分类选择 T+0／T+1 规则

需要检查部分成交时，继续运行[分钟教程](../guide/minutes.md)中的 `minute.py`：它把单根量限降低到 100 份，演示同一订单分多次成交及累计最低佣金。完整时间、滑点与失败语义见[分钟执行契约](../minute-execution.md)。
