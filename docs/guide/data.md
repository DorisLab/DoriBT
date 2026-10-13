# 接入行情

准备**原始行情、交易日历、证券身份和历史规则**，即可把已有 CSV 或 DataFrame 接入 DoriBT。引擎会检查时间轴、字段与规则，然后交给策略和账户执行。

## 日线 CSV

CSV 使用 UTF-8，包含以下列；成交量以股／份计，价格为人民币元、未复权。

```text
session,symbol,status,open,high,low,close,volume,upper_limit,lower_limit
2025-01-02,DEMO,trading,10,10,10,10,500000,12,8
2025-01-03,DEMO,trading,10,10,10,10,500000,12,8
2025-01-06,DEMO,trading,11,11,11,11,500000,12,8
```

保存为 `bars.csv`，运行同一示例的 CSV 入口：

```{literalinclude} ../../examples/csv_backtest.py
:language: python
```

{download}`下载脚本 <../../examples/csv_backtest.py>`。结果同样应为 10895 元。接入自己的数据时，替换脚本中的交易所日历与证券配置；独立日历用于发现整日缺失的行情。

## 从 DataFrame 或数据服务转换

将表格转换为字典行后调用 `MarketData.from_records(...)`，例如 pandas 的 `frame.to_dict("records")`。已有 pandas 表格可以直接转换；接入前统一原始价格、股／份单位、时区和空值格式。

每个交易日、每个声明证券必须恰有一行。停牌用 `status="suspended"`、零量和明确估值；上市前／退市后用对应状态及空价格。没有价格限制时，保留 `upper_limit` 和 `lower_limit` 两列并同时留空。

`china_rules` 按证券分类生成历史制度，行情行提供每日涨跌停价与交易状态。特殊证券的分类和规则见[市场规则](../china-market.md)。

## 复权与公司行动

成交和记账始终使用原始价。分红送转通过 `CorporateAction` 输入；策略需要连续研究价格时，通过 `PriceAdjustment` 提供当时可知的单次事件因子，再调用 `ctx.history(..., adjustment="asof")`。

这样，研究窗口获得连续价格，账户按原始价和分红事实记账。完整字段见[行情与数据](../data-contract.md)和[分红送转](../corporate-actions.md)。
