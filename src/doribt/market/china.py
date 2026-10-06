"""Explicit mainland market presets for 2020–2025; no ticker-based inference.

These presets cover daily quantities, tick size, settlement and statutory fees.
Actual daily price limits and listing/suspension facts remain input data.
Sources, execution assumptions and excluded instruments: docs/china-market.md.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from doribt.market.rules import RuleBook, RulePeriod, TradingRule
from doribt.validation import DateLike, day

VERSION = "cn-cash-2020-2025@2026-10-06"
START, END = date(2020, 1, 1), date(2025, 12, 31)
CHINEXT_REFORM = date(2020, 8, 24)
TRANSFER_CUT = date(2022, 4, 29)
STAMP_CUT = date(2023, 8, 28)

SSE_RULES = (
    "https://www.sse.com.cn/lawandrules/sselawsrules2025/repeal/rules/c/c_20200313_10785127.shtml"
)
SZSE_RULES = "https://www.szse.cn/disclosure/notice/general/t20201231_584050.html"
STAR_RULES = "https://edu.sse.com.cn/tib/qa/c/4761956.shtml"
CHINEXT_RULES = "https://investor.szse.cn/index/update/t20200807_580310.html"
ETF_RULES = "https://investor.szse.cn/warning/activities/fundIntroduction/t20210104_584079.html"
STAMP_OLD = "https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/200809/t20080919_76432.htm"
STAMP_NEW = "https://m.mof.gov.cn/czxw/202308/t20230827_3904226.htm"
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


_PROFILES = {
    "sse_main": _Profile("stock", SSE_RULES),
    "szse_main": _Profile("stock", SZSE_RULES),
    "sse_star": _Profile("stock", STAR_RULES, star=True),
    "szse_chinext": _Profile("stock", CHINEXT_RULES, chinext=True),
    "sse_equity_etf": _Profile("etf", SSE_RULES + "; " + ETF_RULES),
    "szse_equity_etf": _Profile("etf", SZSE_RULES + "; " + ETF_RULES),
}


def china_rules(profiles: Mapping[str, str], *, start: DateLike, end: DateLike) -> RuleBook:
    """Build dated rules for explicitly classified securities, inclusive start/end.

    Example: ``china_rules({'A': 'sse_main', 'E': 'szse_equity_etf'},
    start='2020-01-01', end='2025-12-31')``. Profiles identify the market, not
    a security by its name. Cross-border, bond, gold and money ETFs are excluded.
    """
    first, last = day(start), day(end)
    if not START <= first <= last <= END:
        raise ValueError("China presets require 2020-01-01 <= start <= end <= 2025-12-31")
    if not profiles:
        raise ValueError("at least one explicit market profile is required")
    periods = []
    for symbol, name in profiles.items():
        if name not in _PROFILES:
            raise ValueError(f"unknown China market profile: {name}")
        profile = _PROFILES[name]
        transitions = _transitions(profile, first, last)
        for begin, stop in zip(transitions, transitions[1:], strict=False):
            periods.append(
                RulePeriod(
                    symbol=symbol,
                    start=begin,
                    end=stop - timedelta(days=1),
                    rule=_rule(profile, begin),
                    source=_sources(profile),
                    version=VERSION + ":" + name,
                )
            )
    return RuleBook(tuple(periods))


def _transitions(profile: _Profile, first: date, last: date) -> list[date]:
    changes: list[date] = []
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
        sell_minimum=200 if profile.star else 100,
        sell_step=1 if profile.star else 100,
        order_maximum=maximum,
        settlement_days=1,
        stamp_duty_sell=stamp if stock else 0,
        transfer_fee=transfer if stock else 0,
        instrument_kind=profile.kind,
    )


def _sources(profile: _Profile) -> str:
    if profile.kind == "etf":
        return profile.source
    return "; ".join((profile.source, TRANSFER_SOURCE, STAMP_OLD, STAMP_NEW))
