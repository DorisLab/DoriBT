# 接入自己的行情

数据准备需要四部分：**原始行情、独立交易日历、证券身份、按日期生效的规则**。引擎负责验证和执行，不替你下载或补齐它们。

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

{download}`下载脚本 <../../examples/csv_backtest.py>`。结果同样应为 10895 元。实际数据需替换脚本中的独立日历与证券配置；不能用行情中已有的日期代替独立日历来检查是否漏交易日。

## 从 DataFrame 或数据服务转换

将表格转换为字典行后调用 `MarketData.from_records(...)`，例如 pandas 的 `frame.to_dict("records")`。pandas 不是引擎依赖。数据服务的复权、成交量单位、时区及缺失值应在适配层明确转换。

每个交易日、每个声明证券必须恰有一行。停牌用 `status="suspended"`、零量和明确估值；上市前／退市后用对应状态及空价格。没有价格限制时，保留 `upper_limit` 和 `lower_limit` 两列并同时留空。

`china_rules` 只生成显式分类的基础制度，不生成每日涨跌停价，也不核验供应商的证券分类。ST 等特殊状态须另外提供已核验规则，详见[市场支持矩阵](../china-market.md)。

## 复权与公司行动

成交和记账始终使用原始价。分红送转通过 `CorporateAction` 输入；策略需要连续研究价格时，通过 `PriceAdjustment` 提供当时可知的单次事件因子，再调用 `ctx.history(..., adjustment="asof")`。

不能同时使用整段前复权价记账和手工增加现金分红，否则会重复计入收益。完整字段、验证规则及来源要求见[数据参考](../data-contract.md)和[权益参考](../corporate-actions.md)。
