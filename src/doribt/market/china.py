"""有核验范围的沪深现金账户历史预设，不按证券代码猜分类。

These presets cover daily quantities, tick size, settlement and statutory fees.
Actual daily price limits and listing/suspension facts remain input data.
Sources, execution assumptions and excluded instruments: docs/china-market.md.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from doribt.market.overrides import RuleOverride
from doribt.market.rules import RuleBook, RulePeriod, TradingRule
from doribt.validation import DateLike, day

VERSION = "cn-cash-2015-2026@2026-10-12"
START, END = date(2015, 9, 9), date(2026, 10, 12)
STAR_START = date(2019, 7, 22)
CHINEXT_REFORM = date(2020, 8, 24)
TRANSFER_CUT = date(2022, 4, 29)
STAMP_CUT = date(2023, 8, 28)
RULES_2026 = date(2026, 7, 6)

SSE_RULES = (
    "https://www.sse.com.cn/lawandrules/sselawsrules2025/repeal/rules/c/c_20200313_10785127.shtml"
)
SZSE_RULES = "https://www.szse.cn/disclosure/notice/general/t20201231_584050.html"
STAR_RULES = "https://edu.sse.com.cn/tib/qa/c/4761956.shtml"
CHINEXT_RULES = "https://investor.szse.cn/index/update/t20200807_580310.html"
ETF_RULES = "https://investor.szse.cn/warning/activities/fundIntroduction/t20210104_584079.html"
STAMP_OLD = "https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/200809/t20080919_76432.htm"
STAMP_NEW = "https://shanghai.chinatax.gov.cn/zcfw/zcfgk/yhs/202308/t468451.html"
SSE_NEW = (
    "https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/"
    "c/c_20260424_10816482.shtml"
)
SZSE_NEW = "https://docs.static.szse.cn/www/lawrules/rule/trade/W020260424690713155663.pdf"
TRANSFER_2015 = "https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20150912_3988866.shtml"
ETF_T0 = "https://edu.sse.com.cn/best/article/mcontent/c/4731123.shtml"
SZSE_T0 = "https://www.szse.cn/disclosure/notice/general/t20150109_501348.html"
SZSE_BOND = "https://investor.szse.cn/knowledge/fund/etf/t20170503_538835.html"
SZSE_GOLD = "https://investor.szse.cn/knowledge/fund/etf/t20170503_538836.html"
SSE_T0 = "https://www.sse.com.cn/lawandrules/sselawsrules/repeal/rules/c/c_20230418_5720107.shtml"
TRANSFER_SOURCE = (
    "https://www.hkex.com.hk/-/media/HKEX-Market/Services/Rules-and-Forms-and-Fees/"
    "Rules/SEHK/Securities/Rule-Update_Rules-of-the-Exchange/"
    "049_22_SEHK_Reduction-of-transfer-fee_e_markup.pdf"
)


@dataclass(frozen=True)
class _Profile:
    kind: Literal["stock", "etf"]
    source: str
    star: bool = False
    chinext: bool = False
    settlement: int = 1
    sell_step: int = 100


_PROFILES = {
    "sse_main": _Profile("stock", SSE_RULES),
    "szse_main": _Profile("stock", SZSE_RULES),
    "sse_star": _Profile("stock", STAR_RULES, star=True),
    "szse_chinext": _Profile("stock", CHINEXT_RULES, chinext=True),
    "sse_equity_etf": _Profile("etf", SSE_RULES + "; " + ETF_RULES),
    "szse_equity_etf": _Profile("etf", SZSE_RULES + "; " + ETF_RULES),
    "sse_bond_etf": _Profile("etf", SSE_RULES + "; " + ETF_T0, settlement=0),
    "szse_bond_etf": _Profile(
        "etf", SZSE_RULES + "; " + SZSE_T0 + "; " + SZSE_BOND, settlement=0, sell_step=1
    ),
    "sse_gold_etf": _Profile("etf", SSE_RULES + "; " + ETF_T0, settlement=0),
    "szse_gold_etf": _Profile(
        "etf", SZSE_RULES + "; " + SZSE_T0 + "; " + SZSE_GOLD, settlement=0, sell_step=1
    ),
    "sse_cross_border_t0_etf": _Profile("etf", SSE_RULES + "; " + SSE_T0, settlement=0),
    "szse_cross_border_t0_etf": _Profile("etf", SZSE_RULES + "; " + SZSE_T0, settlement=0),
}


def china_rules(
    profiles: Mapping[str, str],
    *,
    start: DateLike,
    end: DateLike,
    overrides: Sequence[RuleOverride] = (),
) -> RuleBook:
    """按明确分类建立历史预设，并应用有证券/profile 和日期范围的字段覆盖。

    Example: ``china_rules({'A': 'sse_main', 'E': 'szse_equity_etf'},
    start='2020-01-01', end='2025-12-31')``. Profiles identify the market, not
    a security by its name. Cross-border T+0 profiles require verified eligibility.
    Money and commodity-futures ETFs are excluded. Dates are inclusive.
    """
    first, last = day(start), day(end)
    if not START <= first <= last <= END:
        raise ValueError("China presets require 2015-09-09 <= start <= end <= 2026-10-12")
    if not profiles:
        raise ValueError("at least one explicit market profile is required")
    periods = []
    for symbol, name in profiles.items():
        if name not in _PROFILES:
            raise ValueError(f"unknown China market profile: {name}")
        profile = _PROFILES[name]
        begin = max(first, STAR_START) if profile.star else first
        if begin > last:
            raise ValueError(f"no verified dates for China market profile: {name}")
        transitions = _transitions(profile, begin, last)
        for begin, stop in zip(transitions, transitions[1:], strict=False):
            periods.append(
                RulePeriod(
                    symbol=symbol,
                    start=begin,
                    end=stop - timedelta(days=1),
                    rule=_rule(profile, begin),
                    source=_sources(profile, begin),
                    version=VERSION + ":" + name,
                )
            )
    book = RuleBook(tuple(periods), preset_version=VERSION, profiles=tuple(profiles.items()))
    return book.with_overrides(overrides)


def _transitions(profile: _Profile, first: date, last: date) -> list[date]:
    changes: list[date] = [RULES_2026]
    if profile.kind == "stock":
        changes.extend((TRANSFER_CUT, STAMP_CUT))
    if profile.chinext:
        changes.append(CHINEXT_REFORM)
    return [
        first,
        *sorted(change for change in changes if first < change <= last),
        last + timedelta(days=1),
    ]


def _rule(profile: _Profile, session: date) -> TradingRule:
    stock = profile.kind == "stock"
    stamp = Decimal(".001") if session < STAMP_CUT else Decimal(".0005")
    transfer = Decimal(".00002") if session < TRANSFER_CUT else Decimal(".00001")
    maximum = 1_000_000
    if profile.star:
        maximum = 100_000
    elif profile.chinext and session >= CHINEXT_REFORM:
        maximum = 300_000
    return TradingRule(
        price_tick=".01" if stock else ".001",
        buy_minimum=200 if profile.star else 100,
        buy_step=1 if profile.star else 100,
        sell_minimum=200 if profile.star else profile.sell_step,
        sell_step=1 if profile.star else profile.sell_step,
        order_maximum=maximum,
        settlement_days=profile.settlement,
        stamp_duty_sell=stamp if stock else 0,
        transfer_fee=transfer if stock else 0,
        instrument_kind=profile.kind,
    )


def _sources(profile: _Profile, session: date) -> str:
    current = SSE_NEW if "sse.com.cn" in profile.source else SZSE_NEW
    rules = profile.source if session < RULES_2026 else profile.source + "; " + current
    if profile.kind == "etf":
        return rules
    return "; ".join((rules, TRANSFER_2015, TRANSFER_SOURCE, STAMP_OLD, STAMP_NEW))
