"""Corporate-action facts. Execution and tax treatment belong to the account."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .validation import DateLike, Number, amount, day, integer


@dataclass(frozen=True, kw_only=True)
class CorporateAction:
    action_id: str
    symbol: str
    kind: Literal["distribution", "rights_issue", "merger", "delisting"]
    announced: DateLike
    record_date: DateLike
    ex_date: DateLike
    source: str
    cash_per_share: Number = 0
    bonus_per_share: Number = 0
    pay_date: DateLike | None = None
    share_listing_date: DateLike | None = None

    def __post_init__(self) -> None:
        for field in ("action_id", "symbol", "source"):
            value = getattr(self, field)
            if not value or value.strip() != value:
                raise ValueError(f"{field} must be non-empty without surrounding whitespace")
        if self.kind not in {"distribution", "rights_issue", "merger", "delisting"}:
            raise ValueError("unknown corporate-action kind")
        for field in ("announced", "record_date", "ex_date"):
            object.__setattr__(self, field, day(getattr(self, field)))
        if not day(self.announced) <= day(self.record_date) < day(self.ex_date):
            raise ValueError("action dates require announced <= record_date < ex_date")
        cash = amount(self.cash_per_share, "cash_per_share")
        bonus = integer(self.bonus_per_share, 1_000_000, "bonus_per_share", 0, 100_000_000)
        object.__setattr__(self, "cash_per_share", Decimal(cash) / 10_000)
        object.__setattr__(self, "bonus_per_share", Decimal(bonus) / 1_000_000)
        self._validate_settlement(cash, bonus)

    def _validate_settlement(self, cash: int, bonus: int) -> None:
        if self.kind == "distribution" and not (cash or bonus):
            raise ValueError("distribution requires cash or bonus shares")
        if self.kind != "distribution" and (cash or bonus):
            raise ValueError("cash and bonus fields belong to distributions")
        for field, required in (("pay_date", bool(cash)), ("share_listing_date", bool(bonus))):
            raw = getattr(self, field)
            if (raw is not None) != required:
                raise ValueError(f"{field} is required exactly when its entitlement is positive")
            if raw is not None:
                when = day(raw)
                if when < day(self.ex_date):
                    raise ValueError(f"{field} must not precede ex_date")
                object.__setattr__(self, field, when)
