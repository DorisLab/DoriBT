# 沪深现金账户历史预设与规则覆盖

`china_rules(profiles, start=..., end=..., overrides=...)` 为明确分类的证券建立历史
`RuleBook`。0.5.0 核验范围为 **2015-09-09 至 2026-10-12**；科创板从
**2019-07-22** 起提供规则。越界和未知分类失败，不把新制度套回整个历史。

```python
from doribt import china_rules

rules = china_rules(
    {"600519.SH": "sse_main", "159915.SZ": "szse_equity_etf"},
    start="2016-01-01",
    end="2026-10-12",
)
```

把 `rules` 传入 `MarketData.from_records/from_csv/from_minutes`。证券名只是标识，
不从代码前缀推断市场。分类须对应请求区间内的真实身份和资格；`Instrument.kind`
与预设不一致会失败。混合包含科创板的长历史时，科创板规则从开市日期开始，之前的行情
必须是 `unlisted`；提前声明为交易中会因缺少历史规则失败。

## 支持矩阵

本页数量上限对应交易所限价申报范围。执行仍采用独立的下一 bar 开盘与滑点模型，
不模拟限价队列、盘中触价和市价申报保护。

| 分类 | 买入最小量/增量 | 卖出最小量/增量 | 单笔上限 | tick | 买入后可卖 |
| --- | --- | --- | --- | --- | --- |
| `sse_main`、`szse_main` 普通主板 A 股 | 100/100 | 100/100 | 100 万股 | 0.01 元 | 下一交易日 |
| `sse_star` 科创板普通流通股 | 200/1 | 200/1 | 10 万股 | 0.01 元 | 下一交易日 |
| `szse_chinext` 创业板普通流通股 | 100/100 | 100/100 | 2020-08-24 前 100 万，此日起 30 万股 | 0.01 元 | 下一交易日 |
| `sse_equity_etf`、`szse_equity_etf` 境内股票 ETF | 100/100 | 100/100 | 100 万份 | 0.001 元 | 下一交易日 |
| `sse_bond_etf`、`sse_gold_etf` | 100/100 | 100/100 | 100 万份 | 0.001 元 | 当日成交后 |
| `szse_bond_etf`、`szse_gold_etf` | 100/100 | 1/1 | 100 万份 | 0.001 元 | 当日成交后 |
| `sse_cross_border_t0_etf`、`szse_cross_border_t0_etf` | 100/100 | 100/100 | 100 万份 | 0.001 元 | 当日成交后 |

跨境 T+0 分类仅适用于**当期具有当日回转资格**的跨境 ETF，不代表所有境外投资产品。
调用者须核对基金事实和适用名单。货币、商品期货 ETF、LOF、北交所、B 股、存托凭证、
ETF 申赎和融资融券仍不在本矩阵中。

不足正常最小卖出量的剩余持仓允许一次完整清仓；不声称覆盖所有券商的零股拆分申报方式。
固定股数 `ctx.order` 越过上限拒绝，持续目标每个证券每天至多生成一张符合上限的子委托。
完成该子委托不等于完成整体目标；跨日拆分不表示同一开盘无限次拆单。

`settlement_days` 是买入后等待的**交易日数**：0 为当日可卖，1 为下一交易日。
这个字段只控制批次可卖日，不描述清算完成、资金可用或现金可取出的全部制度。
分钟策略仍须等待成交确认，最早下一根 bar 提交/执行后续交易。

## 历史费用与日期

| 成交日期区间 | 股票卖出印花税 | 股票双向过户费 |
| --- | --- | --- |
| 2015-09-09 至 2022-04-28 | 0.001 | 0.00002 |
| 2022-04-29 至 2023-08-27 | 0.001 | 0.00001 |
| 2023-08-28 至 2026-10-12 | 0.0005 | 0.00001 |

表内 ETF 买卖不另计这两项。数值均为小数比例，并按成交日生效。
2015-08-01 已完成沪深过户费计费基数统一；更早沪市面值计费、最低收费及旧股息税
尚需独立模型。因此，本预设没有通过放宽日期检查来宣称支持更早历史。

`Costs.commission` 是券商佣金假设，可包含经手费/证管费，但应排除引擎已另计的
印花税与过户费。它不是实际券商报价。2023 年经手费下调不能在已含规费的佣金之外
再自动收费；不同历史报价、最低佣金减免和费用打包方式由用户明确输入。

股息税属于独立账户政策，见[权益模型](corporate-actions.md)。交易规则覆盖不会改变
税务身份与股息税政策版本。

## 按证券和日期覆盖规则

`RuleOverride` 必须恰好指定 `symbol` 或 `profile`，并提供闭区间日期、非空
`changes`、原因 `reason`、来源 `source` 与自定义 `version`。
`changes` 的键必须是 `TradingRule` 字段；声明保存只读副本。

```python
from doribt import RuleOverride, china_rules

rules = china_rules(
    {"DEMO": "sse_equity_etf"},
    start="2025-01-02",
    end="2025-01-03",
    overrides=[
        RuleOverride(
            symbol="DEMO",
            start="2025-01-03",
            end="2025-01-03",
            changes={"settlement_days": 0},
            reason="测试同日买卖的 T+0 情景",
            source="用户研究假设",
            version="t0-scenario-1",
        ),
    ],
)
```

这只改变 DEMO 在 2025-01-03 成交买入的可卖延迟。2025-01-02 仍按 T+1；
覆盖日期之外及其他字段继续沿用预设。对于股票，覆盖可卖延迟也不会移除成交日印花税。

已有规则簿也可使用 `rules.with_overrides([...])`，返回独立对象。
profile 覆盖例如 `RuleOverride(profile="sse_main", ...)`，会应用于规则簿内已声明
此 profile 的证券；自定义规则簿没有分类时不能猜测匹配。优先级为：

1. 内置或调用者明确构造的基础规则。
2. 用户 profile 覆盖。
3. 用户证券覆盖。

同级同证券同字段的有效期重叠会失败，即便值相同；不同字段允许重叠。
证券层优先于 profile 层，不依赖列表或分次调用顺序。仅替换声明字段，
覆盖后每一层的完整规则须通过数量、tick、比例与类型校验。
未知证券/profile、覆盖日期越出基础规则或跨越缺口均失败，不能以 override 扩大
未经核验的官方范围。高级调用者仍可明确构造自己的历史 `RuleBook`。

覆盖会在官方断点及覆盖起止日切分 `RulePeriod`，保留其余官方变化。
例如只覆盖 `settlement_days`，不会掩盖 2023-08-28 印花税减半。
买入批次在成交时固定可卖交易日；之后的规则不会追溯解锁旧批次或重新锁定已可卖股份。

行情指纹与 `run_info.data.rule_provenance` 保存规则包版本、分类及全部覆盖声明，
最终生效规则仍在 `run_info.data.rules`。改变原因或覆盖，即便数值相同，也产生不同
来源指纹。规则簿和 RunInfo 为独立快照，新增覆盖不会改变旧运行。
研究性的 T+0 覆盖不会成为该品种的官方交易资格。

完整的 1/5 分钟做 T、原生 T+0 与 T+1 底仓比较见[分钟教程](guide/minutes.md#分钟做-t-与日期化覆盖)。

## 每日事实与执行边界

预设提供数量、报价、可卖延迟与上述法定费用。**真实每日 upper_limit/lower_limit
仍由行情输入提供**，包括除权参考价、风险警示、IPO 无涨跌幅限制日及退市整理过渡。
确认无价格涨跌幅限制时明确填空；不能把“无价格涨跌幅限制”当成不存在临停或其他约束。

2020-08-24 部分创业板 ETF 的涨跌幅改为 20%，当期名单包括 159915。
2023-04-10 主板注册制 IPO 前五个交易日无涨跌幅限制。
2026-07-06 沪深主板风险警示股涨跌幅调整为 10%，盘后固定价格交易扩围，上交所基金
收盘阶段改为集合竞价。2026 规则来源已进入新规则段；这些特殊状态和交易阶段不会由
普通 profile 或可卖延迟自动生成。ST/风险警示的额外日买入限制、退市整理、重新上市
等仍需独立的当期规则，不能直接冒用普通股票分类。

分钟仅接收当前 09:30–11:30、13:00–15:00 网格；输入 `phase="auction"` 的 bar
估值但不模拟成交。提供方须正确标记集合竞价、盘中停牌及 2016 年短暂指数熔断期间
不可交易的 bar，不能用普通可成交数据补齐停牌。盘后时段、市价/价格笼子、竞价排队
和临停触发重建不在当前成交模型中。行情真实边界不会被规则覆盖静默改写。

## 依据与核验

- 上交所[2020 历史规则及修订](https://www.sse.com.cn/lawandrules/sselawsrules2025/repeal/rules/c/c_20200313_10785127.shtml)、深交所[2006 基础交易规则](https://www.szse.cn/disclosure/notice/general/t20060515_499577.html)及[2020 规则](https://www.szse.cn/disclosure/notice/general/t20201231_584050.html)：数量、报价与交收；已被替代的版本仍作为当期历史依据。
- 所司[2015 费用统一说明](https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20150912_3988866.shtml)、港交所[中国结算 2022 过户费修订对照](https://www.hkex.com.hk/-/media/HKEX-Market/Services/Rules-and-Forms-and-Fees/Rules/SEHK/Securities/Rule-Update_Rules-of-the-Exchange/049_22_SEHK_Reduction-of-transfer-fee_e_markup.pdf)：注意 2022-04-29 成交生效日与后来规则文字更新日期的区别。
- 财政部[2008 单边印花税](https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/200809/t20080919_76432.htm)、税务机关[2023 减半公告](https://shanghai.chinatax.gov.cn/zcfw/zcfgk/yhs/202308/t468451.html)及深交所[经手费调整](https://www.szse.cn/disclosure/notice/t20230818_602805.html)。
- 上交所[科创板问答](https://edu.sse.com.cn/tib/qa/c/4761956.shtml)、深交所[创业板 2020 规则](https://docs.static.szse.cn/www/disclosure/notice/general/W020200612831351578076.pdf)与[涨跌幅调整基金名单](https://docs.static.szse.cn/www/aboutus/trends/conference/W020200821767425488573.pdf)。
- 上交所[债券/黄金 ETF 当日回转说明](https://edu.sse.com.cn/best/article/mcontent/c/4731123.shtml)及[债券 ETF 业务指南](https://www.sse.com.cn/lawandrules/guide/jjznlc/c/c_20200722_3986154.shtml)；深交所[债券 ETF](https://investor.szse.cn/knowledge/fund/etf/t20170503_538835.html)与[黄金 ETF](https://investor.szse.cn/knowledge/fund/etf/t20170503_538836.html)数量和报价说明。
- 沪市[跨境当日回转通知](https://www.sse.com.cn/lawandrules/sselawsrules/repeal/rules/c/c_20230418_5720107.shtml)、深市[2015-01-19 生效通知及名单](https://www.szse.cn/disclosure/notice/general/t20150109_501348.html)。产品资格仍须按历史事实确认。
- 上交所[2026 修订说明](https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20260424_10816474.shtml)及[正式规则与暂缓条文](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml)、深交所[2026 规则](https://docs.static.szse.cn/www/lawrules/rule/trade/W020260424690713155663.pdf)。

[历史权益示例](https://github.com/DorisLab/DoriBT/blob/main/examples/historical_rules.py)继续使用
超捷股份公开分配事实与人工行情，独立预期为 500 元分红、800 股转增、交易费用 29.32 元、
股息税 100 元、期末现金 19870.68 元。它不代表该股历史收益。
