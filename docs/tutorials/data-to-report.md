---
myst:
  html_meta:
    description: "把 CSV 或 pandas DataFrame 原始行情接入 DoriBT，运行参数化策略，核对费用与基准，导出并验证 CSV／JSON 研究报告。"
---

# 数据到报告

**目标**：把一份原始行情表交给引擎，运行带明确费用和参数的策略，输出可读回、可复现的研究结果。

使用标准库和 DoriBT，把六日人工行情保存为 `tutorial-bars.csv`，再生成 `data-report/`。已有 DataFrame 的接法在最后一节。

## 1. 建立一个干净的研究目录

先按[安装指南](../guide/install.md)安装，在一个新的工作目录把各段 Python 代码顺序保存为 `tutorial_data_report.py`。代码不需要仓库内部模块。

数据必须有四部分：原始行情、独立日历、证券声明和按日期生效的规则。本例只声明一只股票型 ETF；真实工作中应先从有授权的数据源准备这四部分。

```python
import csv
import hashlib
import json
from pathlib import Path

from doribt import (
    Backtest,
    Benchmark,
    Context,
    Costs,
    Instrument,
    MarketData,
    Metric,
    Parameter,
    ParameterSet,
    ResearchOutput,
    RunConfig,
    china_rules,
)

csv_path = Path("tutorial-bars.csv")
csv_text = """session,symbol,status,open,high,low,close,volume,upper_limit,lower_limit
2025-01-02,DEMO,trading,10,10,10,10,500000,13,8
2025-01-03,DEMO,trading,10,10,10,10,500000,13,8
2025-01-06,DEMO,trading,11,11,11,11,500000,13,8
2025-01-07,DEMO,trading,10.5,10.5,10.5,10.5,500000,13,8
2025-01-08,DEMO,trading,11,11,11,11,500000,13,8
2025-01-09,DEMO,trading,12,12,12,12,500000,13,8
"""
# 使用独占创建，避免覆盖已有行情文件。
with csv_path.open("x", encoding="utf-8", newline="") as stream:
    stream.write(csv_text)

calendar = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09"]
instruments = [Instrument(symbol="DEMO", kind="etf")]
rules = china_rules({"DEMO": "szse_equity_etf"}, start=calendar[0], end=calendar[-1])
source = "数据到报告教程：人工六日价格、成交量和价格边界"
data = MarketData.from_csv(
    csv_path,
    calendar=calendar,
    instruments=instruments,
    rules=rules,
    source=source,
)
print("输入指纹：", data.fingerprint)
```

本例使用固定的 13／8 元价格边界。接入真实行情时，填写每日对应的涨跌停价与证券分类。

真实表格中，价格为人民币元、未复权，成交量为整数股／份。没有价格限制时，两列保留并同时留空；停牌不能简单删行。`calendar` 不能用 `sorted(frame.session.unique())` 代替独立日历，否则漏了一整天行情也可能无法发现。

## 2. 用字典行检查 CSV 接入是否一致

`from_csv` 和 `from_records` 接受相同字段。先用标准库读回相同文件，核对等价输入的指纹：

```python
with csv_path.open(encoding="utf-8", newline="") as stream:
    records = list(csv.DictReader(stream))
records_data = MarketData.from_records(
    records,
    calendar=calendar,
    instruments=instruments,
    rules=rules,
    source=source,
)
assert records_data.fingerprint == data.fingerprint
assert len(data.sessions) == 6
assert data.symbols == ("DEMO",)
```

相同指纹表示 CSV 和字典行入口构造了相同的行情。原始价格、成交量、状态和公司行动字段见[行情与数据](../data-contract.md)。

## 3. 运行一个有明确预期的策略

先用简单买入持有验证接入，避免同时调试数据与复杂信号。本例目标 90%，初始 10000 元，佣金万三、每单最低 5 元；参数会随运行记录保存。

```python
schema = ParameterSet({"allocation": Parameter(type="float", default=0.9, minimum=0, maximum=1)})


def strategy(ctx: Context, *, allocation: float) -> None:
    ctx.record(close=float(ctx.history("DEMO", bars=1)[-1]), target_weight=allocation)
    ctx.target_weights({"DEMO": allocation})


config = RunConfig(
    initial_cash=10_000,
    costs=Costs(commission=0.0003, minimum_commission=5),
)
result = Backtest(data, config=config).run(strategy, parameter_schema=schema)
assert len(result.fills) == 1
assert result.fills[0].quantity == 900
assert result.fills[0].session.isoformat() == "2025-01-03"
assert int(result.cash_units[-1]) == 995 * 10_000
assert int(result.equity_units[-1]) == 11795 * 10_000
print("期末权益：", result.equity[-1])
```

可以手算：首日收盘提出目标，第二日开盘以 10 元买入 900 份，9000 元成交额加 5 元最低佣金，剩余现金 995 元；末日估值 `995 + 900 × 12 = 11795` 元。

默认相同权重延续原股数目标，本例因此持续持有 900 份。研究每日再平衡时设置 `rebalance=True`，即可比较新增成交和费用。样本末尾按剩余持仓估值。

## 4. 加入基准与自己的研究指标

```python
benchmark = Benchmark(
    sessions=data.sessions,
    prices=data.prices("close")[:, 0],
    name="DEMO 人工价格基准",
    source=source,
)
result = result.analyze(
    "cost_check",
    lambda r: ResearchOutput(
        metrics={
            "fees_per_fill": Metric(
                sum(fill.fees for fill in r.fills) / len(r.fills) if r.fills else None,
                unit="CNY",
                description="每笔成交的平均交易费用",
            )
        }
    ),
)
report = result.report(benchmark=benchmark, periods_per_year=252, risk_free_rate=0)
for name in ("total_return", "max_drawdown", "total_fees", "excess_total_return", "win_rate"):
    print(name, report.stats[name])
print("参数：", result.run_info.to_dict()["parameters"])
```

期末总收益为 17.95%，价格基准涨幅为 20%，累计超额为 −2.05 个百分点。价格基准从首个价格归一化；策略账户的现金配置与交易费用，可以从账户和成交记录中进一步解释。

本例持续持仓，已关闭交易轮次为零，`win_rate` 返回 `None`。交易轮次和指标定义见[参数与研究输出](../research-contract.md)。

## 5. 导出，并读回核对

```python
output = result.export(Path("data-report"), benchmark=benchmark, daily=True)
saved_report = json.loads((output / "report.json").read_text(encoding="utf-8"))
assert saved_report["stats"]["total_return"] == report.stats["total_return"]

manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
for filename, expected in manifest["files"].items():
    content = (output / filename).read_bytes()
    assert len(content) == expected["bytes"]
    assert hashlib.sha256(content).hexdigest() == expected["sha256"]
print("导出文件校验通过：", len(manifest["files"]))
print("报告目录：", output)
```

在脚本所在的新工作目录运行：

```sh
python tutorial_data_report.py
```

建议按这个顺序看结果：

1. `fills.csv`：是不是在预期日期、按预期数量与价格成交
2. `account.csv`、`positions.csv`：现金与权益能否重建，持仓和可卖量是否符合预期
3. `report.json`：日频统计、每日账户、月收益、交易盈亏与口径定义
4. `research.json`：策略记录的收盘价／权重，以及 `cost_check` 自定义费用指标
5. `run.json`、`manifest.json`：参数、配置、来源、版本、输入指纹和各文件校验和

校验通过后，可以确认报告文件与导出时的内容一致。整数 `*_units` 金额除以 10000，即为人民币元。

输出父目录必须已经存在，目标目录必须尚不存在；再次实验请换新工作目录，或分别修改 CSV 与报告名称。脚本不会覆盖输入样本或已有报告。需要 PNG 时先安装 `doribt[plot]`，在 `export` 增加 `plot=True`，输出会多一个 `equity.png`。完整文件与失败语义见[导出契约](../results.md#导出契约)。

## 6. 已有 pandas DataFrame 怎么接

pandas 是你的数据准备工具，不是 DoriBT 的必需依赖。若已安装 pandas，可以把主脚本中的 `MarketData.from_csv(...)` 替换为下面的等价入口；其余日历、证券、规则和来源仍沿用同一份配置：

```text
import pandas as pd

frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
data = MarketData.from_records(
    frame.to_dict("records"),
    calendar=calendar,
    instruments=instruments,
    rules=rules,
    source=source,
)
```

`dtype=str` 保留代码前导零与 CSV 中的价格文本，`keep_default_na=False` 避免空边界变成浮点 NaN。已有其他来源的 DataFrame，先将 `trade_date`、`ts_code`、`vol` 等供应商列名映射为本教程的字段。

按字段转换空值：上市前价格留空，停牌填写估值与零成交量，交易行填写有效原始价。分钟 DataFrame 使用带时区的时间戳和 `MarketData.from_minutes`，详见[接入行情](../guide/data.md)。

接入核对通过后，再把买入持有替换为[多 ETF 轮动](etf-rotation.md)或[分钟做 T](intraday-t.md)。同一套输入与报告接口，可以继续用于组合轮动和分钟策略。
