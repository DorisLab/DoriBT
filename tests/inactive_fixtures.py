"""可公开的生命周期样例；所有价格和规则均为人工数据。"""

from collections.abc import Mapping
from dataclasses import asdict, fields, replace
from datetime import date, timedelta

import numpy as np

from doribt import Instrument, MarketData, RuleBook, RulePeriod, TradingRule, WeightTargets

CASES = (
    "listing",
    "never",
    "omitted",
    "staggered",
    "suspended",
    "replace",
    "delisted",
    "pending_delisted",
    "cash",
    "rules",
    "zero",
    "unchanged",
    "frequent",
    "last",
)


def state_at(name, index, column):
    if name in ("never", "omitted") and column == 0:
        return "unlisted"
    if name in ("listing", "staggered", "cash", "rules") and index < 2 + column:
        return "unlisted"
    if name in ("suspended", "replace") and column == 0 and index in (2, 3, 4):
        return "suspended"
    if name in ("delisted", "pending_delisted") and column == 0 and index >= 4:
        return "delisted"
    return "trading"


def weights_for(name):
    a = [0, 0, 0.5, 0.5, 0, 0, 0, 0]
    b = [0.5] * 8
    if name in ("never", "omitted", "zero", "last"):
        a = [0] * 8
    if name in ("listing", "staggered", "cash", "rules"):
        b = [0, 0, 0, 0.5, 0.5, 0, 0.5, 0.5]
    if name in ("suspended", "pending_delisted", "unchanged"):
        a = [0.5] * 8
    if name == "delisted":
        a = [0.5, 0.5, 0, 0, 0, 0, 0, 0]
    if name in ("replace", "frequent"):
        a = [0.5, 0.5, 0, 0.3, 0.3, 0, 0.5, 0]
    if name == "zero":
        b = [0] * 8
    if name == "last":
        a[-1] = 0.5
    return {"B": b} if name == "omitted" else {"A": a, "B": b}


def scenario(name, sizing="close", rebalance=False, full_rules=False, symbols=("A", "B")):
    days = [date(2025, 1, 2) + timedelta(days=i) for i in range(8)]
    rule = TradingRule(
        price_tick=".01",
        buy_minimum=100,
        buy_step=100,
        sell_step=100,
        settlement_days=0,
        stamp_duty_sell=".0005",
        transfer_fee=".00001",
    )
    rows, periods = [], []
    for column, symbol in enumerate(symbols):
        active = [i for i in range(8) if state_at(name, i, column) in ("trading", "suspended")]
        if active or full_rules:
            first, last = (0, 7) if full_rules else (active[0], active[-1])
            for begin, end in ((first, min(4, last)), (max(first, 5), last)):
                if begin <= end:
                    current = (
                        replace(rule, buy_step=1, sell_step=1, settlement_days=1)
                        if name == "rules" and begin >= 5
                        else rule
                    )
                    periods.append(
                        RulePeriod(
                            symbol=symbol,
                            start=days[begin],
                            end=days[end],
                            rule=current,
                            source="人工历史规则",
                            version=str(begin),
                        )
                    )
    for index, session in enumerate(days):
        for column, symbol in enumerate(symbols):
            status = state_at(name, index, column)
            price = 10 if status in ("trading", "suspended") else None
            volume = 100_000 if status == "trading" else 0
            if name == "pending_delisted" and column == 0:
                volume = 0
            if name in ("cash", "suspended", "replace", "frequent") and status == "trading":
                volume = 137
            rows.append(
                dict(
                    session=session,
                    symbol=symbol,
                    status=status,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=volume,
                    upper_limit=None,
                    lower_limit=None,
                )
            )
    data = MarketData.from_records(
        rows,
        calendar=days,
        instruments=[Instrument(symbol=s, kind="etf") for s in symbols],
        rules=RuleBook(tuple(periods)),
        source="编译生命周期人工样例",
    )
    weights = {s: w for s, w in weights_for(name).items() if s in symbols}
    return data, WeightTargets(
        sessions=data.timeline, weights=weights, sizing=sizing, rebalance=rebalance
    )


def ledger(result):
    """保留完整数组、完整审计字段及顺序；仅排除来源与后端标识。"""
    payload = {}
    for field in fields(result):
        if field.name in ("backend", "run_info"):
            continue
        value = getattr(result, field.name)
        if isinstance(value, np.ndarray):
            value = value.tolist()
        elif isinstance(value, Mapping):
            value = dict(value)
        elif isinstance(value, tuple) and value and hasattr(value[0], "__dataclass_fields__"):
            value = [asdict(item) for item in value]
        payload[field.name] = value
    return payload
