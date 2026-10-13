"""有范围、有来源的字段覆盖；先解析优先级，再生成无重叠规则段。"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from doribt.serialization import digest, encode
from doribt.validation import DateLike, day

if TYPE_CHECKING:
    from doribt.market.rules import RuleBook, RulePeriod


@dataclass(frozen=True, kw_only=True)
class RuleOverride:
    """在闭区间内覆盖 TradingRule 字段，symbol 与 profile 必须恰选其一。

    changes 保存独立只读副本。reason、source、version 说明用户情景，
    不会改写行情、停牌、公司行动或已经买入批次的可卖日期。
    """

    start: DateLike
    end: DateLike
    changes: Mapping[str, object]
    reason: str
    source: str
    version: str
    symbol: str | None = None
    profile: str | None = None

    def __post_init__(self) -> None:
        from doribt.market.rules import TradingRule

        object.__setattr__(self, "start", day(self.start))
        object.__setattr__(self, "end", day(self.end))
        if day(self.start) > day(self.end):
            raise ValueError("override start must not follow end")
        if (self.symbol is None) == (self.profile is None):
            raise ValueError("override requires exactly one symbol or profile")
        for name in ("symbol", "profile", "reason", "source", "version"):
            value = getattr(self, name)
            if value is None and name in ("symbol", "profile"):
                continue
            if not isinstance(value, str) or not value.strip() or value.strip() != value:
                raise ValueError(
                    f"override {name} must be non-empty without surrounding whitespace"
                )
        allowed = {item.name for item in fields(TradingRule)}
        changes = dict(self.changes)
        if not changes or not set(changes) <= allowed:
            raise ValueError("override changes must name non-empty TradingRule fields")
        if any(
            value is not None and not isinstance(value, (str, int, float, bool, Decimal))
            for value in changes.values()
        ):
            raise ValueError("override changes must contain scalar rule values")
        object.__setattr__(self, "changes", MappingProxyType(dict(sorted(changes.items()))))
        encode(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        """返回独立、可序列化的覆盖声明。"""
        return {
            "symbol": self.symbol,
            "profile": self.profile,
            "start": day(self.start).isoformat(),
            "end": day(self.end).isoformat(),
            "changes": dict(self.changes),
            "reason": self.reason,
            "source": self.source,
            "version": self.version,
        }


def _key(item: RuleOverride) -> tuple[int, str]:
    return int(item.symbol is not None), encode(item.to_dict())


def _targets(item: RuleOverride, book: "RuleBook") -> tuple[str, ...]:
    if item.symbol is not None:
        return (item.symbol,)
    return tuple(symbol for symbol, profile in book.profiles if profile == item.profile)


def _validate_range(item: RuleOverride, symbol: str, periods: Sequence["RulePeriod"]) -> None:
    cursor = day(item.start).toordinal()
    for period in periods:
        if period.symbol != symbol or day(period.end).toordinal() < cursor:
            continue
        if day(period.start).toordinal() > cursor:
            break
        cursor = day(period.end).toordinal() + 1
        if cursor > day(item.end).toordinal():
            return
    raise ValueError(f"override is outside covered rule dates for {symbol}")


def _validate_conflicts(symbol: str, items: Sequence[RuleOverride]) -> None:
    for index, current in enumerate(items):
        for previous in items[:index]:
            same_level = (previous.symbol is None) == (current.symbol is None)
            overlap = max(day(previous.start), day(current.start)) <= min(
                day(previous.end), day(current.end)
            )
            shared = previous.changes.keys() & current.changes.keys()
            if same_level and overlap and shared:
                raise ValueError(f"conflicting overrides for {symbol}: {sorted(shared)}")


def _split(period: "RulePeriod", items: Sequence[RuleOverride]) -> list["RulePeriod"]:
    # 整数边界允许 date.max 后的排他终点，但不构造超出范围的日期。
    begin, stop = day(period.start).toordinal(), day(period.end).toordinal() + 1
    boundaries = {begin, stop}
    for item in items:
        boundaries.update(
            (
                max(begin, day(item.start).toordinal()),
                min(stop, day(item.end).toordinal() + 1),
            )
        )
    result = []
    ordered = sorted(boundaries)
    for start, end in zip(ordered, ordered[1:], strict=False):
        first = date.fromordinal(start)
        active = [item for item in items if day(item.start) <= first <= day(item.end)]
        rule = period.rule
        for specific in (False, True):
            changes: dict[str, Any] = {
                name: value
                for item in active
                if (item.symbol is not None) == specific
                for name, value in item.changes.items()
            }
            # 同级不同字段一起校验，证券层不能掩盖无效的 profile 配置。
            rule = replace(rule, **changes)
        sources = "; ".join(dict.fromkeys([period.source, *(item.source for item in active)]))
        version = period.version
        if active:
            version += "+override:" + digest([item.to_dict() for item in active])[:16]
        result.append(
            replace(
                period,
                start=first,
                end=date.fromordinal(end - 1),
                rule=rule,
                source=sources,
                version=version,
            )
        )
    return result


def apply_overrides(book: "RuleBook", overrides: Sequence[RuleOverride]) -> "RuleBook":
    from doribt.market.rules import RuleBook

    if not isinstance(overrides, Sequence) or isinstance(overrides, (str, bytes)):
        raise ValueError("overrides must be a sequence of RuleOverride values")
    if not overrides:
        return book
    if any(not isinstance(item, RuleOverride) for item in overrides):
        raise ValueError("overrides must contain RuleOverride values")
    items = tuple(sorted((*book.overrides, *overrides), key=_key))
    base = book._base_periods or book.periods
    grouped: dict[str, list[RuleOverride]] = {}
    for item in items:
        targets = _targets(item, book)
        if not targets:
            raise ValueError(f"override profile has no matching securities: {item.profile}")
        for symbol in targets:
            _validate_range(item, symbol, base)
            grouped.setdefault(symbol, []).append(item)
    for symbol, selected in grouped.items():
        _validate_conflicts(symbol, selected)
    periods = []
    for period in base:
        selected = [
            item
            for item in grouped.get(period.symbol, ())
            if day(item.start) <= day(period.end) and day(item.end) >= day(period.start)
        ]
        periods.extend(_split(period, selected))
    result = RuleBook(tuple(periods), preset_version=book.preset_version, profiles=book.profiles)
    object.__setattr__(result, "overrides", items)
    object.__setattr__(result, "_base_periods", base)
    return result
