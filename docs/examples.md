# 可运行示例

先[安装包](guide/install.md)，下载仓库源码后，在仓库根目录执行下列命令。除特别说明外，行情、日历和价格边界都是人工数据，不需要行情账号，不代表可交易策略表现。

所有回测示例从顶层 `doribt` 导入，统一使用 `RunConfig`。Numba 示例加 `--backend numba`，并预先安装对应 extra。可单独下载脚本；带辅助模块的示例需同时下载依赖。

| 场景 | 命令 | 阅读重点 |
| --- | --- | --- |
| 第一次回测 | `python examples/quickstart.py` | 三日输入、下一 bar 执行与费用 |
| CSV 行情 | `python examples/csv_backtest.py` | 先按[数据教程](guide/data.md)准备工作目录的 bars.csv |
| 预计算均线 | `python examples/sma.py` | 不含未来信息的窗口、WeightTargets |
| 买入持有／均线／轮动 | `python examples/strategies.py` | 同一数据的函数策略与共享资金 |
| 分钟订单 | `python examples/minute.py` | 部分成交、T+1、累计佣金 |
| 滑点边界 | `python examples/slippage.py` | 高点买入／低点卖出、三种边界策略与成本 |
| 分钟预计算 | `python examples/minute.py --precomputed` | PositionTargets 和事件分段 |
| 数据字段 | `python examples/market_data.py` | 状态、规则与数据指纹 |
| 分红送转 | `python examples/dividends.py` | 现金／股份分日到账、税务 |
| 历史规则 | `python examples/historical_rules.py` | 公开分派事实＋人工价格，原始价与时点复权 |

## 参数化研究

`research.py` 导入同目录的 `strategies.py`，请保留两个文件。安装 `doribt[plot]` 后运行：

```sh
python examples/research.py --plot --output my-report
```

`my-report` 必须尚不存在。此示例包含参数声明、最低佣金配置、`ctx.record`、基准、自定义分析和日频导出。

```{literalinclude} ../examples/research.py
:language: python
```

{download}`下载 research.py <../examples/research.py>` · {download}`下载 strategies.py <../examples/strategies.py>`

其余脚本：[完整 examples 目录](https://github.com/DorisLab/DoriBT/tree/main/examples)。
