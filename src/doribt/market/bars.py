"""Row parsing. Missing fields never imply an ordinary tradable session."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

from doribt.market.clock import timestamp
from doribt.market.instruments import TradingStatus
from doribt.market.rules import TradingRule
from doribt.validation import MAX_PRICE, DateLike, day, integer


@dataclass(frozen=True)
class Bar:
    """Validated storage row; price fields use integer 1/10,000 yuan units."""

    session: date
    symbol: str
    status: TradingStatus
    open: int
    high: int
    low: int
    close: int
    volume: int
    upper_limit: int | None
    lower_limit: int | None
    timestamp: datetime | None = None
    phase: str = "continuous"

    def __post_init__(self) -> None:
        object.__setattr__(self, "session", day(self.session))
        if self.timestamp is not None:
            point = timestamp(self.timestamp)
            if point.date() != self.session:
                raise ValueError("timestamp and trading session disagree")
            object.__setattr__(self, "timestamp", point)
        if self.phase not in {"continuous", "auction"}:
            raise ValueError("phase must be continuous or auction")
        if not self.symbol or self.symbol.strip() != self.symbol:
            raise ValueError("bar symbol must be non-empty without surrounding whitespace")
        if not isinstance(self.status, TradingStatus):
            raise ValueError("bar status must be TradingStatus")
        active = self.status in (TradingStatus.TRADING, TradingStatus.SUSPENDED)
        for field in ("open", "high", "low", "close"):
            value = integer(getattr(self, field), 1, field, int(active), MAX_PRICE)
            object.__setattr__(self, field, value)
        volume = integer(self.volume, 1, "volume", 0, 1_000_000_000_000)
        object.__setattr__(self, "volume", volume)
        self._validate_limits(active)

    def _validate_limits(self, active: bool) -> None:
        if (self.upper_limit is None) != (self.lower_limit is None):
            raise ValueError("price limits must both be supplied or explicitly absent")
        for field in ("upper_limit", "lower_limit"):
            if (raw := getattr(self, field)) is not None:
                object.__setattr__(self, field, integer(raw, 1, field, 1, MAX_PRICE))
        if not active and any((self.open, self.high, self.low, self.close, self.volume)):
            raise ValueError("unlisted/delisted rows require empty prices and zero volume")
        if not active and self.upper_limit is not None:
            raise ValueError("inactive rows cannot have price limits")


def optional_price(value: object, name: str) -> int | None:
    if value is None or value == "":
        return None
    return integer(value, 10_000, name, 1, MAX_PRICE)


def _identity(record: Mapping[str, object]) -> tuple[date, str, TradingStatus]:
    raw_session, symbol, raw_status = record["session"], record["symbol"], record["status"]
    if not isinstance(raw_session, (str, date)) or not isinstance(symbol, str):
        raise ValueError("session and symbol must be explicitly identified")
    if not isinstance(raw_status, str):
        raise ValueError("status must be trading, suspended, unlisted or delisted")
    try:
        status = TradingStatus[raw_status.upper()]
    except KeyError as error:
        raise ValueError(f"unknown trading status: {raw_status}") from error
    return day(raw_session), symbol, status


def parse_bar(record: Mapping[str, object]) -> Bar:
    required = {
        "session",
        "symbol",
        "status",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "upper_limit",
        "lower_limit",
    }
    if missing := required - record.keys():
        raise ValueError(f"missing bar columns: {', '.join(sorted(missing))}")
    session, symbol, status = _identity(record)
    upper = optional_price(record["upper_limit"], "upper_limit")
    lower = optional_price(record["lower_limit"], "lower_limit")
    if (upper is None) != (lower is None):
        raise ValueError("price limits must both be supplied or explicitly absent")
    volume = integer(record["volume"], 1, "volume", 0, 1_000_000_000_000)
    fields = ("open", "high", "low", "close")
    values = [optional_price(record[name], name) for name in fields]
    if status in (TradingStatus.UNLISTED, TradingStatus.DELISTED):
        if any(value is not None for value in values) or volume or upper is not None:
            raise ValueError("unlisted/delisted rows require empty prices and zero volume")
        return Bar(session, symbol, status, 0, 0, 0, 0, 0, None, None)
    if any(value is None for value in values):
        raise ValueError("trading/suspended rows require explicit OHLC valuation prices")
    op, high, low, close = (int(value) for value in values if value is not None)
    return Bar(session, symbol, status, op, high, low, close, volume, upper, lower)


def validate_bar(bar: Bar, rule: TradingRule) -> None:
    prices = (bar.open, bar.high, bar.low, bar.close)
    if not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high:
        raise ValueError(f"invalid OHLC range: {bar.symbol} {bar.session}")
    boundaries = () if bar.upper_limit is None else (bar.upper_limit, bar.lower_limit)
    if any(price % rule.tick_units for price in (*prices, *boundaries) if price is not None):
        raise ValueError(f"price is off tick: {bar.symbol} {bar.session}")
    if bar.upper_limit is not None and bar.lower_limit is not None:
        if not bar.lower_limit <= bar.low <= bar.high <= bar.upper_limit:
            raise ValueError(f"OHLC outside declared daily limits: {bar.symbol} {bar.session}")
    if bar.status == TradingStatus.SUSPENDED and bar.volume != 0:
        raise ValueError("suspended session must have zero volume")


def calendar_days(values: list[DateLike]) -> tuple[date, ...]:
    days = tuple(day(value) for value in values)
    if not days or any(left >= right for left, right in zip(days, days[1:], strict=False)):
        raise ValueError("calendar must be non-empty and strictly increasing without duplicates")
    return days
