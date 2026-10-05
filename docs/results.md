# 结果、指标与研究记录

正式 `BacktestResult` 表示一次共享现金账户运行。证券列顺序为 `result.symbols`，行顺序为 `result.sessions`；不会把参数组合放进证券列。金额账本与分析浮点数分别使用，指标不反向修改账本。

## 日常用法

```python
result = Backtest(data, initial_cash=100_000).run(
    moving_average,
    parameters={"fast": 5, "slow": 20, "allocation": 0.95},
    backend="python",
)
benchmark = Benchmark(
    sessions=data.sessions,
    prices=index_levels,
    name="自备指数",
    source="说明价格或全收益口径及来源",
)
print(result.stats(benchmark=benchmark, periods_per_year=252, risk_free_rate=0))
figure = result.plot(benchmark=benchmark)  # 需要 doribt[plot]
figure.savefig("comparison.png")
result.export("new-report", benchmark=benchmark, periods_per_year=252, plot=True)
```

上例变量由研究脚本提供；完整可运行版本见 [research.py](../examples/research.py)。策略的签名是 `moving_average(ctx, *, fast, slow, allocation)`。`parameters` 接受 JSON 对象／列表／标量，不接受 NaN、Infinity、非字符串键或任意 Python 对象。运行前检查函数签名并复制嵌套参数；参数实际传入回调，记录的是初始值，回调内对复制后可变参数的修改不污染调用者。`WeightTargets` 自带其完整预计算输入，不再接收额外策略参数。

基础结果仍可直接读 `equity`、`cash`、`holdings`、`sellable`、`orders`、`fills`、`intents` 和权益／税务记录。`*_units` 为整数万分之一元，`equity` 等便利属性为元。`close_units` 保留每个证券的记账估值价，`pending_shares` 为尚未入账但已计入经济权益的股份；不能只用已入账持仓解释全部净值。

## 指标口径

令 `E[t]` 为日终权益，`E[0]` 为首日空仓初始资金。引擎没有期间外部入金或出金，不在最后一天强制清仓。净值包含应收分红、待入账股份及已确认税款负债。

| 输出 | 定义 |
| --- | --- |
| `nav` | `E[t] / initial_cash`，首日为 1 |
| `returns` | 相邻日终 `E[t]/E[t-1]-1`；第一行 0 只用于对齐，不进入风险样本 |
| `total_return` | 末日权益／初始资金 − 1 |
| `drawdown` / `max_drawdown` | `1-E[t]/历史最高权益`；最高值包含初始资金，结果为正数损失比例 |
| `annual_return` | `(1+total_return) ** (P/N) - 1`，`N` 为相邻收盘区间数，`P` 为显式年化周期 |
| `annual_volatility` | 收益样本标准差（`ddof=1`）× `sqrt(P)` |
| `sharpe` | `mean(r-q) / sample_std(r) * sqrt(P)` |
| `sortino` | `mean(r-q) / sqrt(mean(min(r-q,0)^2)) * sqrt(P)`；分母对所有区间取均值 |
| `total_fees` | 实际成交佣金＋印花税＋过户费；同时提供三个分项，股息税单列 |
| `dividend_tax` | 已确认的股息税，包含已扣和尚未扣收；`unpaid_dividend_tax` 为末日未扣收部分 |
| `order_count` / `fill_count` | 当日委托／实际成交条数；不是完整买卖交易次数或胜率 |
| `unfilled_order_count` / `partial_order_count` | 无成交／部分成交的委托数；持续目标的不同交易日尝试分别计数 |

`risk_free_rate` 是年有效利率，默认 0；每区间门槛 `q=(1+rate)**(1/P)-1`。它只参与分析，不向现金账户计息。未指定 `periods_per_year` 时不计算年化、Sharpe、Sortino 或年化跟踪指标；非零无风险利率此时会报错。即便输入日线，也不猜测应采用 250、252 或其他天数。不按自然日跨度悄悄换一种 CAGR 算法。

少于两个收益区间时样本风险指标为 `None`，无收益区间时年化收益也为 `None`。零标准差／零下行偏差对应比率为 `None`，不显示无穷大。前一日权益为零或负数时下一期收益不可定义，数组用 NaN，`undefined_return_periods` 计数，风险指标为 `None`，不丢掉失败区间再算好看的统计。浮点计算超出可表示范围的指标也为 `None`。导出用 JSON `null` 或 CSV 空单元格，不写非标准 JSON NaN／Infinity。

## 基准

`Benchmark(sessions=..., prices=..., name=..., source=...)` 接受正的、有限的价格或指数水平，复制输入并要求日期与回测结果逐项相同；不会自动重排、前填、下载或复权。第一收盘归一化为 1。纯价格指数与全收益指数由来源明确，DoriBT 不把价格指数当成包含分红的收益指数。

- `benchmark_total_return`、`benchmark_max_drawdown` 使用同样的首日基准。
- `excess_total_return` 是策略累计收益减基准累计收益，非相对财富比值。
- `beta` 为策略与基准收益的样本协方差／基准样本方差；零方差时不可定义。
- `annual_tracking_error` 为每期策略减基准收益的样本标准差 × `sqrt(P)`。
- `information_ratio` 为每期超额收益均值／样本标准差 × `sqrt(P)`；零跟踪误差时不可定义。

基准使用持有指数的理论路径，不替基准扣佣金或模拟成交；如需可交易基准，应另跑一份具有同样费用和交易约束的策略来比较。

## 图表

`plot()` 返回 [Matplotlib Figure](https://matplotlib.org/stable/api/_as_gen/matplotlib.figure.Figure.html)，上方显示净值与可选基准，下方显示负向回撤。可以继续使用 Figure／Axes 编辑，或保存 PNG、SVG、PDF。库不打开桌面窗口、不调用 `pyplot.show()`、不修改全局 Matplotlib 后端。中文标签需要用户环境中适用的字体；默认示例使用英文图例。

`plot` 是可选安装项；导入和运行基础引擎不加载 Matplotlib。`export(..., plot=True)` 才请求绘图，缺依赖会明确报错并清理此次临时输出。

## 导出契约

`result.export(path, ...)` 返回绝对目录路径。父目录必须存在，目标必须尚不存在。不提供隐式覆盖开关。所有文件先写到同级临时目录，读回校验成功后，通过 Windows 不替换 rename 或 Linux `renameat2(RENAME_NOREPLACE)` 一次发布；竞争进程抢先创建同名目录也不会被覆盖。写入／绘图／校验／发布失败时清理本次暂存，保留之前的成功目录。保证进程可见性和不覆盖，不宣称断电持久化；其他操作系统目前不支持该发布操作。

| 文件 | 内容 |
| --- | --- |
| `account.csv` | 每日现金、可用现金、权益、应收、税负债、净值、收益、回撤 |
| `positions.csv` | 每日每标的数量、可卖量、待入账股份、估值价、含待入账股份的价值 |
| `orders.csv` / `fills.csv` / `intents.csv` | 委托、成交、意图及目标调整，带关联 ID 和原因 |
| `entitlements.csv` / `corporate_events.csv` | 登记权益、应收／到账／入账事件 |
| `taxes.csv` / `tax_payments.csv` / `tax_lots.csv` | 税款确认、扣收和期末剩余税务批次 |
| `ledger.json` | 以上离散账本记录的有类型版本，保留空值与嵌套调整信息 |
| `stats.json` | 指标以及本次指定的年化周期和无风险利率 |
| `run.json` | 实际运行假设、初始资金、参数、模型、来源、规则、权益和依赖版本 |
| `benchmark.json` | 指定基准时保存全部基准输入及来源 |
| `equity.png` | 请求绘图时保存的净值／回撤图 |
| `manifest.json` | `doribt.export/1`、数据／运行指纹、单位与空值约定，以及其他每个文件的 SHA-256 和字节数 |

CSV 为 UTF-8，日期为 ISO 8601，嵌套字段为 JSON 字符串，空表保留列头。整数记账字段保持整数；金额／价格 `units` 是 `0.0001 CNY`，税务每股收入 `income_micros` 是 `0.000001 CNY/share`。`positions.csv` 包含所有证券／交易日组合；未上市或已退市的空价格以内部 0 表示，不作为可交易价格。

当前交付标准 CSV／JSON，不要求 pandas／Arrow。Parquet、交互报告与产品侧资产管理可在实际消费者需要时追加。

## 来源记录与复现边界

`result.run_info` 是不可变 JSON 快照；`to_dict()` 每次返回新副本。它包含：

- 数据完整指纹、来源、证券顺序、日历、带有效期的规则、公司行动及带可知日期的研究复权因子；规则／行动另有 SHA-256。
- 初始资金及实际编译使用的佣金 ppm、最低佣金记账单位、滑点 ticks、税务政策版本。
- 收盘决定／下一输入开盘执行、固定股数、卖出后按声明证券顺序买入、原始价、不强制清仓等假设。
- 回调模块／名称与可读取时的源代码哈希；预计算权重则保留完整日期和数值及哈希；显式参数的初始快照。
- Python、操作系统、DoriBT、NumPy，使用 Numba 时另记 Numba／llvmlite 版本；安装包内 Python 引擎文件的整体内容指纹。

不读取环境变量、不抓取闭包／全局变量／对象状态、不复制策略源代码或原始行情。回调来源不可读取时明确为 `null`，外部状态标记 `not_captured`。调用者仍需保留自己的原始数据、脚本、锁定环境以及显式随机种子；参数不能存放凭据，来源描述也不应带认证信息。指纹可以核对输入和程序是否一致，不能证明任意有外部状态的 Python 回调完全可复现。

`run_info.fingerprint` 标识执行记录；同一结果使用不同分析假设导出时，执行指纹保持相同，`stats.json`、基准和文件清单哈希随分析输入变化。可选绘图库版本不算执行依赖，其环境由研究项目的锁文件保留。
