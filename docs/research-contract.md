# 参数、研究输出与默认报告

参数描述既可驱动 Python 策略，也可用于客户端表单；标准报告和自定义研究输出共同保存。本页定义字段、校验、扩展和统计口径。

## 输入

- `RunConfig` 汇总初始资金、`Costs`（佣金比例、最低佣金）、`BarExecution` 和后端；统一日线／分钟撮合模型。禁止与 Backtest 的独立构造参数混用，避免覆盖优先级不清。日期、证券、周期仍由经过验证的 MarketData 提供，不在引擎中下载、裁剪或猜测行情。
- `Parameter` 声明类型、默认值、说明、单位、上下界、步长或选项；`ParameterSet` 校验未知键、缺失值、类型和范围，在首次策略调用前失败。声明和实际参数都记录到运行来源。Python 函数参数接口继续可用。
- 金额与比例保持已有精度要求；零佣金／零最低佣金合法。费用默认值不是必须接受的券商报价。

## 输出

- `ctx.record(name=value)` 记录当次回调的命名数值；同一时点同名重复写入失败，未记录的时点为空，不自动向前填充。记录器只在运行内部生存，每次 run 隔离。
- `ResearchOutput` 支持带说明／单位的标量、显式时间对齐曲线和同构表格。数据必须有限且可序列化，名称唯一；构造时快照，结果通过 `with_outputs` 返回新对象，不修改标准账本。
- `result.analyze(name, callable)` 是运行结束后的分析扩展：函数读取结果并返回 ResearchOutput；失败向调用者传播，不发布半份输出。不在撮合循环执行分析器，不让预计算路径退化成逐 bar Python 回调。
- 标准导出附带研究输出 JSON，纳入同一校验清单。自定义字段位于独立命名空间，不能覆盖账户、成交或标准指标。

## 默认报告

- `stats()` 使用逐输入周期口径；`report()` 默认按交易日最后一个时点汇总，以 252 个交易日／年、零无风险利率分析，配置和定义随报告保存。
- 每日收益从初始资金开始，首日交易影响不能丢失；月度收益按相邻月末权益计算，首月相对初始资金。基准可传同 bar 或精确日历对齐的日线序列，首个提供价格是归一化起点。
- 标准报告包含日净值、月收益、收益风险／基准指标、双边成交额除以日均权益的累计换手率、最大回撤持续交易日数，以及交易与持仓成本分析。
- 交易分析采用移动加权平均成本，买入费用计入成本、卖出费用扣减收益；送转在除权日增加含待到账股份的经济持仓，现金分红与分红税单独列示。`已实现价格盈亏 + 未实现价格盈亏 + 已确认分红 - 已计提分红税 = 总权益 - 初始资金`，不将税务批次冒充交易成本批次。
- 一轮交易定义为某证券从零持仓到重新归零；未平仓轮次单列。胜率、平均盈利／平均亏损比、利润因子只统计已关闭轮次的扣交易费用价格盈亏，明确不包含现金分红／分红税；持有期为日历天。逐笔卖出同时保留移动成本、费用和已实现价格盈亏。
- 不可定义的指标使用 null，包括没有已平仓交易、没有亏损分母和无法确定基准风险；不以零或无穷大伪装有效统计。

## 源码组织与验收

`market/` 管数据／规则，`accounting/` 管账户／权益／费用／记录，`runtime/` 管策略与执行生命周期，`kernels/` 管数值计算，`reporting/` 管分析与导出，`research/` 管参数和输出协议。用户通过 `from doribt import ...` 导入，公开入口不随内部目录变化；内部模块路径不作为用户依赖入口。

验收覆盖可配置费用实际改变成交与资金、参数缺失／误型／越界、研究记录隔离及过期回调、扩展结果不可覆盖标准字段、导出校验和／失败原子性、分钟按日统计、手算盈亏／分红送转拆分、基准和月度收益，以及两个后端与隔离 wheel 中的完整公开示例。

## 使用入口

```python
from doribt import Backtest, Costs, Parameter, ParameterSet, RunConfig

schema = ParameterSet(
    {
        "allocation": Parameter(
            type="float",
            default=0.8,
            minimum=0,
            maximum=1,
            step=0.05,
            label="目标仓位",
            unit="ratio",
        ),
    }
)


def strategy(ctx, *, allocation):
    ctx.record(allocation=allocation)
    ctx.target_weights({ctx.symbols[0]: allocation})


# data 为调用者准备的 MarketData；费用由账户实际约定填写。
config = RunConfig(costs=Costs(commission=0.0001, minimum_commission=0))
result = Backtest(data, config=config).run(strategy, parameter_schema=schema)
report = result.report()  # 默认日频、252 个交易日／年、无风险利率 0
print(report.stats)
result.export("new-report", daily=True)
```

`RunConfig.schema().to_dict()`、`schema.to_dict()` 提供可序列化描述，`RunConfig.from_dict(values)` 校验表单数据；运行配置的 JSON 字段为 initial_cash、commission、minimum_commission、participation、slippage_kind、slippage_value、backend。佣金比例用小数（万一为 0.0001），最低佣金单位元、精确到分；后者不是每次部分成交重复收取，而是一个订单累计计算。固定 tick 滑点数值为整数档位，bps 为单边基点（5 表示 0.05%），volume_impact 为冲击系数。每个模型仍按内核支持精度／上限校验。

策略声明只支持 int／float／str／bool 标量；无声明 parameters 仍接受 JSON 对象和列表。声明的缺省参数由 default 补齐，未知键失败；step 从 minimum（未指定则 0）起算并参与校验，用于表单和后续参数扫描，不等于已提供优化器。跨字段关系由策略检查。后端可在 run 时显式覆盖，实际值写入运行信息。

```python
from doribt import Metric, ResearchOutput, Series, Table

result = result.analyze(
    "risk",
    lambda r: ResearchOutput(
        metrics={"drawdown_score": Metric(r.max_drawdown, unit="ratio")},
        tables={
            "notes": Table(
                columns=["item", "value"],
                rows=[
                    {"item": "sample", "value": "synthetic"},
                ],
            )
        },
    ),
)
# 预计算曲线不需要切换成逐 bar 回调：
result = result.with_outputs(
    "signal",
    ResearchOutput(
        series={
            "allocation": Series(sessions=result.sessions, values=[0.8] * len(result.sessions)),
        }
    ),
)
```

Series 必须逐时点对齐完整结果，稀疏曲线用 None；不能把日线曲线悄悄广播到分钟。表格为声明列名的 JSON 标量行，空表也保留列名。数值不接受 NaN／Infinity，record 和数值输出支持归一化 NumPy 数值标量。重复 namespace／字段失败；analyze 是纯结果后处理契约，调用者保留分析代码和外部输入，不承诺自动捕获闭包或阻止任意 Python 副作用。

## 文件与分析口径

- `result.stats()`、`result.plot()`、不指定 daily 的 export 保留输入周期口径。`result.report()` 返回 ResearchReport；to_dict() 是可直接 JSON 序列化的副本。
- `result.export(..., daily=True)` 写出 report.json（stats／daily／monthly／trades／definitions），stats.json 同步采用日频报告，图表也按日采样；account.csv 和 positions.csv 始终保留原始 bar，供核对。
- 所有导出均写 research.json；其 outputs 使用独立 namespace。所有文件纳入原子发布和 manifest 校验，标准导出 schema 为 doribt.export/1。
- 报告的价格盈亏按移动平均分摊，属于分析值，不反写定点账本。送转不新增现金成本，除权时将原成本分摊到含待到账股份的数量；如原持仓已卖出，新取得的送转股份成本为零。现金分红归已确认收入，税款按已计提金额，支付日变化不重复影响收益。
- `with_outputs` 不改变执行指纹；不同扩展内容、分析口径、基准通过各文件哈希区分。用户入口为顶层 doribt 的导出对象。
