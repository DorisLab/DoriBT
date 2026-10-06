"""Security identity and explicit daily trading status."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Literal


class TradingStatus(IntEnum):
    TRADING = 0
    SUSPENDED = 1
    UNLISTED = 2
    DELISTED = 3


@dataclass(frozen=True, kw_only=True)
class Instrument:
    symbol: str
    kind: Literal["stock", "etf"]

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol.strip() != self.symbol:
            raise ValueError("symbol must be non-empty without surrounding whitespace")
        if self.kind not in {"stock", "etf"}:
            raise ValueError("baseline instruments must be stock or etf")
