# DoriBT

**面向 A 股研究的 Python 回测引擎。**

Python backtesting for A-share research, with an optional Numba execution backend.

DoriBT 关注交易规则、账户状态、可解释的成交记录与可复现研究。首个交付目标是数据、策略、执行、账户和结果分析基本完整的日线回测引擎，见[开发目标](docs/roadmap.md)。

目前源码已提供多标的共享账户、收盘策略／目标权重、次日开盘执行、分红送转和普通个人股息税，以及 2020–2025 沪深普通股票／境内股票 ETF 的基础规则预设。结果可以计算收益／风险与基准指标、绘图并导出可对账文件和运行来源。真实行情与完整引擎性能验收仍未完成，尚未达到首版目标。原型单标的预算模型保留在 `doribt.experimental` 中。

数据准备入口 `MarketData` 支持带证券标识的 CSV／字典行、历史规则和公司行动验证，见[数据契约](docs/data-contract.md)。完整执行时间和失败语义见[执行模型](docs/execution-model.md)。

## 当前可以做什么

- 多标的共享现金，收盘回调策略或日期对齐的预计算目标权重。
- 收盘确定固定股数，次日开盘先卖后买；资金不足减量，持续目标可以重试。
- 持仓批次、按交易日交收解锁、显式停牌及方向性涨跌停阻止成交。
- 历史数量／价位／费率、佣金与滑点；金额按万分之一元记账，费用按分半入。
- 意图、当日委托、实际成交和原因分别可查，附每日现金／持仓／可卖量／权益。
- 分红登记、应收与到账，送转股份入账与可卖日，独立税务批次、税款计提和扣收。
- 策略参数随运行记录，净值／回撤／风险和基准比较，JSON／CSV 导出；可选 Matplotlib 图表。
- 原始成交价格与按决策时点复权的研究历史分别提供，因子缺失或当时未知时明确报错。
- Python 和可选 Numba 执行同一开盘逻辑；独立 Decimal 账本检查共享资金、费用和交收。

当前要求数据提供层给出原始价格、真实交易日、每日状态／价格边界及有来源的历史规则。`china_rules` 提供显式分类的数量、交收和历史税费，见[市场支持矩阵](docs/china-market.md)。引擎不下载行情、不根据证券代码猜规则，也不提供真实交易接口。[权益与税务模型](docs/corporate-actions.md)只覆盖已明确的普通个人政策和整数股份分配；影响账户的配股、合并等未知行动明确失败。平台适配器尚未实现。

## 快速运行

初始支持范围为 Python 3.13。示例仅使用固定种子的合成数据，无需账号、行情服务或网络数据下载。

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 后：

```sh
git clone https://github.com/DorisLab/DoriBT.git
cd DoriBT
uv sync
uv run python examples/strategies.py
uv run python examples/dividends.py
uv run python examples/historical_rules.py
uv run python examples/research.py
```

使用 Numba：

```sh
uv sync --extra numba
uv run --extra numba python examples/strategies.py --backend numba
```

首次 Numba 调用需要编译，后续调用和缓存行为取决于环境。项目尚未发布 PyPI 安装包，以上命令从源码安装。

## 最小调用

```python
from doribt import Backtest, Context
from examples.strategies import synthetic_market  # 源码仓库自带的人工数据

data = synthetic_market()  # 实际研究替换成自己的 MarketData。


def buy_and_hold(ctx: Context, *, allocation: float) -> None:
    ctx.target_weights({"ALPHA": allocation})


result = Backtest(data, initial_cash=100_000).run(buy_and_hold, parameters={"allocation": 0.95})
print(result.stats())
for fill in result.fills:
    print(fill.session, fill.symbol, fill.quantity, fill.price, fill.fees)
```

此代码从仓库根目录运行。相同权重不每天重算股数；需要按当天权益重新配比时传 `rebalance=True`。`ctx.order(symbol, quantity)` 提交只尝试下一次开盘的有符号股数委托；`ctx.history()` 只返回截至当前收盘的数据，`ctx.account.positions` 和 `ctx.orders` 可查询账户与历史订单。

均线、买入持有、多标的轮动都在[策略示例](examples/strategies.py)中，无需继承基类或修改内核。预计算入口 `WeightTargets(sessions=data.sessions, weights={"ALPHA": weights})` 使用同一执行流程；日期必须完全对齐。首日空仓，最后一次收盘决定不会提前执行；预计算因子是否含未来信息仍需策略自身验证。API 可继续演进，见 [API 设计](docs/api-design.md)。

## 分析与导出

`result.stats()` 不假定年化周期；指定 `periods_per_year=252` 才使用这一年化假设。`Benchmark` 接受与结果完全同日期的价格／指数序列，既不下载行情，也不自动补齐。示例包含参数化均线、基准比较与结果导出：

```sh
uv sync --extra plot
uv run --extra plot python examples/research.py --plot --output results-demo
```

`results-demo` 必须尚不存在，父目录须存在。`result.export("results-demo", periods_per_year=252, plot=True)` 写出每日账户、逐标的持仓、委托、成交、权益、税务、指标和带校验和的来源清单。已有目录不会被覆盖，失败不会发布半份报告。图表也可以直接用 `result.plot(benchmark=...)` 返回的 Matplotlib Figure 编辑、保存；基础安装无图表依赖。指标公式、缺失值及复现边界见[结果与研究记录](docs/results.md)。

原型 `experimental.Backtest` 使用开盘预算模型，与新的固定股数模型语义不同；原说明见[实验模型](docs/model.md)，原示例仍可通过 `examples/sma.py` 运行。

## 开发与检查

```sh
uv sync --locked --extra numba
uv run --no-sync python scripts/check.py --backend numba --audit
```

检查包括格式、静态类型、行为与生成式账本测试、README 示例、覆盖率报告、构建、隔离安装包验证和依赖漏洞审计。CI 分别验证 Windows / Linux 的基础安装与 Numba 安装，并扫描泄露凭据。具体门禁与定向检查见[质量检查](docs/quality.md)；CI 配置不代替实际通过记录。

## 项目状态与参与

开发优先级由维护者的实际研究需求驱动。欢迎提交最小复现、规则依据、错误报告和聚焦的改进，见[贡献说明](CONTRIBUTING.md)。目前不承诺支持响应时间、API 稳定性、完整市场覆盖或特定用途适用性。

项目按 [Apache-2.0](LICENSE) 许可提供；不提供投资建议或收益承诺。
