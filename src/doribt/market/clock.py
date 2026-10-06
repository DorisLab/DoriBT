"""Explicit Shanghai bar-end clock; settlement always uses trading-day ordinals."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from doribt.validation import DateLike, day

SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")


def timestamp(value: object) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(hours=8):
        raise ValueError("timestamp must have explicit Asia/Shanghai +08:00 offset")
    if value.second or value.microsecond:
        raise ValueError("timestamp must be on a whole minute")
    return value.astimezone(SHANGHAI)


def time_points(values: Sequence[DateLike]) -> tuple[date, ...]:
    """Strictly aligned daily dates or aware minute endpoints, never mixed."""

    def parse(value: DateLike) -> date:
        if isinstance(value, datetime) or isinstance(value, str) and "T" in value:
            return timestamp(value)
        return day(value)

    result = tuple(parse(value) for value in values)
    if not result or len({type(value) for value in result}) != 1:
        raise ValueError("time points must be non-empty and of one frequency type")
    if any(a >= b for a, b in zip(result, result[1:], strict=False)):
        raise ValueError("time points must be strictly increasing without duplicates")
    return result


@dataclass(frozen=True)
class MinuteClock:
    frequency: str
    timestamps: tuple[datetime, ...]
    day_indices: tuple[int, ...]

    @classmethod
    def build(cls, sessions: tuple[date, ...], frequency: str) -> "MinuteClock":
        if frequency not in {"1min", "5min"}:
            raise ValueError("minute frequency must be 1min or 5min")
        step = 1 if frequency == "1min" else 5
        points, indices = [], []
        for index, session in enumerate(sessions):
            for start in (time(9, 30), time(13)):
                opening = datetime.combine(session, start, SHANGHAI)
                for minute in range(step, 121, step):
                    points.append(opening + timedelta(minutes=minute))
                    indices.append(index)
        return cls(frequency, tuple(points), tuple(indices))
