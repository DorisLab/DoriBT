"""Exact input conversion for the baseline engine."""

from datetime import date, datetime
from decimal import Decimal, DecimalException, localcontext

MONEY_SCALE = 10_000
MAX_MONEY = 100_000_000_000_000
MAX_PRICE = 10_000_000_000

type DateLike = date | str
type Number = Decimal | int | float | str


def day(value: DateLike) -> date:
    if isinstance(value, datetime):
        raise ValueError("session must be a date, not an intraday timestamp")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("session must use YYYY-MM-DD")
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid session: {value}") from error
    if result.isoformat() != value:
        raise ValueError("session must use YYYY-MM-DD")
    return result


def integer(value: object, scale: int, label: str, minimum: int, maximum: int) -> int:
    try:
        parsed = Decimal(str(value))
        with localcontext() as context:
            context.prec = max(28, len(parsed.as_tuple().digits) + len(str(scale)))
            exact = parsed * scale
    except (DecimalException, TypeError, ValueError) as error:
        raise ValueError(f"{label}: invalid number") from error
    if not exact.is_finite() or exact != exact.to_integral_value():
        raise ValueError(f"{label}: non-finite number or unsupported precision")
    if not minimum <= exact <= maximum:
        raise ValueError(f"{label}: outside supported bounds")
    return int(exact)


def amount(value: Number, label: str = "amount") -> int:
    return integer(value, MONEY_SCALE, label, 0, MAX_MONEY)


def ratio(value: Number, label: str = "rate") -> int:
    return integer(value, 1_000_000, label, 0, 1_000_000)
