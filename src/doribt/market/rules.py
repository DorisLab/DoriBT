"""Explicit historical trading rules, independent of strategy and execution policy."""

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Literal

from doribt.market.overrides import RuleOverride, apply_overrides
from doribt.validation import MAX_PRICE, DateLike, Number, day, integer, ratio


@dataclass(frozen=True, kw_only=True)
class TradingRule:
    price_tick: Number
    buy_minimum: int
    buy_step: int
    sell_step: int
    settlement_days: int
    stamp_duty_sell: Number
    transfer_fee: Number
    allow_odd_lot_liquidation: bool = True
    sell_minimum: int = 1
    order_maximum: int = 1_000_000_000
    instrument_kind: Literal["stock", "etf"] | None = None

    def __post_init__(self) -> None:
        tick = integer(self.price_tick, 10_000, "price_tick", 1, MAX_PRICE)
        object.__setattr__(self, "price_tick", Decimal(tick) / 10_000)
        for name in ("buy_minimum", "buy_step", "sell_step", "sell_minimum", "order_maximum"):
            value = integer(getattr(self, name), 1, name, 1, 1_000_000_000)
            object.__setattr__(self, name, value)
        if self.order_maximum < max(self.buy_minimum, self.sell_minimum, self.sell_step):
            raise ValueError("order maximum must cover both buy and sell minima")
        if self.instrument_kind not in (None, "stock", "etf"):
            raise ValueError("rule instrument kind must be stock or etf")
        settlement = integer(self.settlement_days, 1, "settlement_days", 0, 10)
        object.__setattr__(self, "settlement_days", settlement)
        for name in ("stamp_duty_sell", "transfer_fee"):
            value = ratio(getattr(self, name), name)
            object.__setattr__(self, name, Decimal(value) / 1_000_000)
        if not isinstance(self.allow_odd_lot_liquidation, bool):
            raise ValueError("allow_odd_lot_liquidation must be boolean")

    @property
    def tick_units(self) -> int:
        return integer(self.price_tick, 10_000, "price_tick", 1, MAX_PRICE)


@dataclass(frozen=True, kw_only=True)
class RulePeriod:
    symbol: str
    start: DateLike
    end: DateLike
    rule: TradingRule
    source: str
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", day(self.start))
        object.__setattr__(self, "end", day(self.end))
        if not self.symbol or self.symbol.strip() != self.symbol:
            raise ValueError("rule symbol must be non-empty without surrounding whitespace")
        if day(self.start) > day(self.end):
            raise ValueError("rule start must not follow end")
        if not self.source.strip() or not self.version.strip():
            raise ValueError("rule source and version are required")


@dataclass(frozen=True)
class RuleBook:
    periods: tuple[RulePeriod, ...]
    preset_version: str | None = None
    profiles: tuple[tuple[str, str], ...] = ()
    overrides: tuple[RuleOverride, ...] = field(init=False, default=())
    _base_periods: tuple[RulePeriod, ...] = field(init=False, default=(), repr=False, compare=False)
    _index: Mapping[str, tuple[RulePeriod, ...]] = field(init=False, repr=False, compare=False)
    _starts: Mapping[str, tuple[date, ...]] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        periods = sorted(self.periods, key=lambda p: (p.symbol, day(p.start)))
        object.__setattr__(self, "periods", tuple(periods))
        object.__setattr__(self, "profiles", _profiles(self.profiles, self.periods))
        if self.preset_version is not None and (
            not isinstance(self.preset_version, str) or not self.preset_version.strip()
        ):
            raise ValueError("preset version must be a non-empty string")
        grouped: dict[str, list[RulePeriod]] = {}
        for period in self.periods:
            grouped.setdefault(period.symbol, []).append(period)
        for symbol, periods in grouped.items():
            ordered = sorted(periods, key=lambda item: day(item.start))
            for previous, current in zip(ordered, ordered[1:], strict=False):
                if day(current.start) <= day(previous.end):
                    raise ValueError(f"overlapping rule periods for {symbol}")
        index = {symbol: tuple(items) for symbol, items in grouped.items()}
        starts = {
            symbol: tuple(day(item.start) for item in items) for symbol, items in index.items()
        }
        object.__setattr__(self, "_index", MappingProxyType(index))
        object.__setattr__(self, "_starts", MappingProxyType(starts))

    def with_overrides(self, overrides: Sequence[RuleOverride]) -> "RuleBook":
        """返回合并后的独立规则簿；证券覆盖优先于 profile，同级字段冲突报错。"""
        return apply_overrides(self, overrides)

    def provenance(self) -> dict[str, object]:
        """内置版本、分类和覆盖声明，供数据指纹与运行来源共同冻结。"""
        return {
            "preset_version": self.preset_version,
            "profiles": dict(self.profiles),
            "overrides": [item.to_dict() for item in self.overrides],
        }

    def at(self, symbol: str, session: date) -> RulePeriod:
        position = bisect_right(self._starts.get(symbol, ()), session) - 1
        if position < 0:
            raise ValueError(f"missing historical rule for {symbol} on {session}")
        period = self._index[symbol][position]
        if session > day(period.end):
            raise ValueError(f"missing historical rule for {symbol} on {session}")
        return period


def _profiles(
    values: tuple[tuple[str, str], ...], periods: tuple[RulePeriod, ...]
) -> tuple[tuple[str, str], ...]:
    pairs = tuple((symbol, profile) for symbol, profile in values)
    symbols = {period.symbol for period in periods}
    for symbol, profile in pairs:
        if symbol not in symbols:
            raise ValueError("rule profile symbol must have historical periods")
        if not isinstance(profile, str) or not profile.strip() or profile.strip() != profile:
            raise ValueError("rule profile must be a non-empty string")
    if len(dict(pairs)) != len(pairs):
        raise ValueError("rule profiles must have unique symbols")
    return tuple(sorted(pairs))
