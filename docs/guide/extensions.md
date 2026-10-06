# 扩展研究输出

标准账户与成交字段保持统一，自定义指标、曲线和表格放在独立命名空间，随报告一起导出。

## 在策略中记录

```python
def strategy(ctx):
    closes = ctx.history("ALPHA", bars=20)
    if len(closes) == 20:
        ctx.record(mean_close=float(closes.mean()))
```

运行后从 `result.outputs["strategy"].series["mean_close"]` 读取。未记录的时点为 `None`，不会自动前填；同一时点的同名重复写入失败。记录器只能在当前回调使用。

## 运行后添加指标与表格

```python
from doribt import Metric, ResearchOutput, Table

result = result.analyze(
    "diagnostics",
    lambda r: ResearchOutput(
        metrics={"fill_count": Metric(len(r.fills), unit="count", description="成交笔数")},
        tables={"notes": Table(columns=["说明"], rows=[{"说明": "人工研究示例"}])},
    ),
)
```

`analyze` 接收本次结果并返回 `ResearchOutput`。已有输出可使用 `with_outputs(namespace, output)` 直接附加；两者返回新结果，不修改标准账本。

## 添加预计算曲线

```python
from doribt import ResearchOutput, Series

result = result.with_outputs(
    "signal",
    ResearchOutput(
        series={"allocation": Series(sessions=result.sessions, values=[0.8] * len(result.sessions))}
    ),
)
```

曲线须对齐完整结果时间轴，稀疏值用 `None`。表格行与声明列一致，值为 JSON 标量；数值不接受 NaN／Infinity。重复命名空间会失败，不能覆盖已有标准字段。

任何导出都会写 `research.json`，并纳入统一校验和。扩展不会改变执行指纹；其内容由导出文件哈希标识。完整约定见[研究输出参考](../research-contract.md)。
