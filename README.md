# DoriBT

**面向 A 股研究的 Python 回测引擎。**

Experimental backtesting primitives for A-share research, with an optional Numba backend.

DoriBT 关注交易规则、账户状态、可解释的成交记录与可复现研究。首个交付目标是数据、策略、执行、账户和结果分析基本完整的日线回测引擎，见[开发目标](docs/roadmap.md)。

目前源码提供 `doribt.experimental` 下的单标的日线预算模型，尚未达到这一交付目标。当前能力以本页和[模型说明](docs/model.md)为准。

完整引擎的数据准备入口 `MarketData` 已提供带证券标识的 CSV／字典行、历史规则和公司行动验证，见[数据契约](docs/data-contract.md)及[可执行示例](examples/market_data.py)。它与当前实验回测入口分开；账户和权益记账仍在开发。

## 当前可以做什么

- 一个标的、多个独立参数账户，做多／空仓切换。
- 开盘代理成交、收盘估值，100 份整手、0.001 元价格单位。
- 最低佣金、按分舍入、滑点、显式停牌及方向性涨跌停限制。
- 输出每日现金、持仓、权益、逐笔成交及未成交原因。
- Python 和可选 Numba 两种执行方式；内部金额使用整数分，费用使用整数比例。
- 使用独立 Decimal 账本和手算样例检查行为。

当前模型要求调用者提供对齐的原始价格、真实交易日及每日价格边界，并将决策延迟到可执行的交易日。它不下载行情、不自动识别证券规则，也不提供真实交易接口。完整 T+1 可卖量、多标的共享现金、公司行动和平台适配器尚未实现。详见[模型边界](docs/model.md)和[路线图](docs/roadmap.md)。

## 快速运行

初始支持范围为 Python 3.13。示例仅使用固定种子的合成数据，无需账号、行情服务或网络数据下载。

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 后：

```sh
git clone https://github.com/DorisLab/DoriBT.git
cd DoriBT
uv sync
uv run python examples/sma.py
```

使用 Numba：

```sh
uv sync --extra numba
uv run --extra numba python examples/sma.py --backend numba
```

首次 Numba 调用需要编译，后续调用和缓存行为取决于环境。项目尚未发布 PyPI 安装包，以上命令从源码安装。

## 最小调用

```python
from doribt.experimental import Backtest, CloseSignals, Costs, DailyBars

# 手算样例，全部为人工构造数据。
bars = DailyBars(
    sessions=["2025-01-02", "2025-01-03", "2025-01-06"],
    open=[10.0, 10.0, 11.0],
    close=[10.0, 10.5, 11.0],
    upper_limit=[12.0, 12.0, 12.0],
    lower_limit=[8.0, 8.0, 8.0],
    suspended=[False, False, False],
)
# 每个收盘时点决定持有或空仓，由引擎延迟到下一交易日开盘执行。
signals = CloseSignals(sessions=bars.sessions, hold=[True, False, False])
result = Backtest(bars, initial_cash=10_000, costs=Costs(slippage_ticks=0)).run(signals)
print(result.equity)  # [10000. 10445. 10890.]
print(result.total_return)  # 约 0.089，即 8.9%
print(result.stats())
```

`CloseSignals` 表达收盘后的持有意图，连续 `True` 不每天重新调仓。首日空仓，最后一日收盘信号不会穿越到当日执行；日期必须与行情一致，不静默对齐。完整的均线例子见 [examples/sma.py](examples/sma.py)。

单账户结果直接提供一维权益、现金和持仓，成交带交易日期，收益统计保存本次初始资金。底层 `backtest(bars, regime, config)` 仍可做独立参数账户批量实验，其中 `regime` 必须已延迟；两种入口不能混用时间语义。当前 API 可演进，未来策略／组合接口的职责见 [API 设计](docs/api-design.md)。

## 开发与检查

```sh
uv sync --locked --extra numba
uv run --no-sync python scripts/check.py --backend numba --audit
```

检查包括格式、静态类型、行为与生成式账本测试、README 示例、覆盖率报告、构建、隔离安装包验证和依赖漏洞审计。CI 分别验证 Windows / Linux 的基础安装与 Numba 安装，并扫描泄露凭据。具体门禁与定向检查见[质量检查](docs/quality.md)；CI 配置不代替实际通过记录。

## 项目状态与参与

开发优先级由维护者的实际研究需求驱动。欢迎提交最小复现、规则依据、错误报告和聚焦的改进，见[贡献说明](CONTRIBUTING.md)。目前不承诺支持响应时间、API 稳定性、完整市场覆盖或特定用途适用性。

项目按 [Apache-2.0](LICENSE) 许可提供；不提供投资建议或收益承诺。
