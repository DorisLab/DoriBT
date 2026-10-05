# DoriBT

**面向 A 股研究的 Python 回测引擎。**

Experimental backtesting primitives for A-share research, with an optional Numba backend.

DoriBT 关注交易规则、账户状态、可解释的成交记录与可复现研究。项目处于早期开发阶段；目前可运行的是 `doribt.experimental` 下的单标的日线预算模型，完整 A 股引擎仍在建设中。

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
import numpy as np
from doribt.experimental import Config, DailyBars, backtest

# 手算样例，全部为人工构造数据。
bars = DailyBars(
    sessions=np.array(["2025-01-02", "2025-01-03"], dtype="datetime64[D]"),
    open=np.array([10.0, 11.0]),
    close=np.array([10.5, 11.0]),
    upper_limit=np.array([12.0, 12.0]),
    lower_limit=np.array([8.0, 8.0]),
    suspended=np.array([False, False]),
)
result = backtest(
    bars,
    regime=np.array([1, 0]),  # 已在开盘前确定：进入、退出
    config=Config(initial_cash=10_000, slippage_ticks=0),
)
print(result.equity[:, 0])  # [10445. 10890.]
```

每列是独立账户，`regime=1` 表示希望持有，`0` 表示希望空仓；持有期间不每天调回目标比例。`experimental` 接口可能随开发调整。

## 开发与检查

```sh
uv sync --locked --extra numba
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pytest
uv build
uv run --no-sync python scripts/check_wheel.py
```

GitHub Actions 对 Windows / Linux 的 Python 3.13 执行相同检查和两种后端的示例。CI 状态以实际运行结果为准。

## 项目状态与参与

开发优先级由维护者的实际研究需求驱动。欢迎提交最小复现、规则依据、错误报告和聚焦的改进，见[贡献说明](CONTRIBUTING.md)。目前不承诺支持响应时间、API 稳定性、完整市场覆盖或特定用途适用性。

项目按 [Apache-2.0](LICENSE) 许可提供；不提供投资建议或收益承诺。
