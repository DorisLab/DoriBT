"""Source-provided price adjustments applied only when known at the decision date."""

from dataclasses import dataclass
from decimal import Decimal, DecimalException
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from doribt.market.clock import timestamp
from doribt.validation import DateLike, Number, day

if TYPE_CHECKING:
    from doribt.market.data import MarketData


@dataclass(frozen=True, kw_only=True)
class PriceAdjustment:
    """Multiply prices preceding this action's ex-date by ``factor``.

    This is one event's factor, not a vendor's cumulative latest-date factor.
    Account distributions and the market's reference price can differ, so an
    account's per-share cash entitlement is not used to guess this value.
    """

    action_id: str
    factor: Number
    known_on: DateLike
    source: str

    def __post_init__(self) -> None:
        for name in ("action_id", "source"):
            value = getattr(self, name)
            if not value or value.strip() != value:
                raise ValueError(f"{name} must be non-empty without surrounding whitespace")
        try:
            factor = Decimal(str(self.factor))
        except DecimalException as error:
            raise ValueError("adjustment factor must be a finite positive number") from error
        if not factor.is_finite() or not Decimal("1e-100") <= factor <= Decimal("1e100"):
            raise ValueError("adjustment factor must be positive and within [1e-100, 1e100]")
        object.__setattr__(self, "factor", factor)
        object.__setattr__(self, "known_on", day(self.known_on))


def view_end(data: "MarketData", adjustment: str, as_of: DateLike | None) -> int:
    if adjustment not in {"raw", "asof"}:
        raise ValueError("adjustment must be 'raw' or 'asof'")
    if as_of is None:
        if adjustment == "asof":
            raise ValueError("asof-adjusted prices require an explicit as_of session")
        return len(data.timeline)
    when = timestamp(as_of) if data.clock else day(as_of)
    try:
        return data.timeline.index(when) + 1
    except ValueError as error:
        raise ValueError("as_of must be a supplied trading session") from error


def adjust(
    data: "MarketData",
    values: NDArray[np.float64],
    *,
    start: int,
    end: int,
    symbols: tuple[str, ...],
) -> None:
    """Adjust a writable slice in place; only events crossing its time window matter."""
    first = data.sessions[data.day_index(start)]
    last = data.sessions[data.day_index(end - 1)]
    factors = {item.action_id: item for item in data.adjustments}
    for action in sorted(data.actions, key=lambda item: day(item.ex_date)):
        ex_date = day(action.ex_date)
        if action.symbol not in symbols or not first < ex_date <= last:
            continue
        factor = factors.get(action.action_id)
        if factor is None or day(factor.known_on) > last:
            raise ValueError(f"price adjustment unavailable as of {last}: {action.action_id}")
        column = symbols.index(action.symbol)
        day_index = data.sessions.index(ex_date)
        first_bar = data.clock.day_indices.index(day_index) if data.clock else day_index
        offset = first_bar - start
        prior = values[:offset, column]
        valid = np.isfinite(prior)
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            prior *= float(factor.factor)
        if not np.all(np.isfinite(prior[valid])) or np.any(prior[valid] <= 0):
            raise ValueError(f"adjusted prices exceed floating-point bounds: {action.action_id}")
