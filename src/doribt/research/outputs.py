"""Immutable, finite research values in a namespace separate from accounting."""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import numpy as np

from doribt.market.clock import time_points
from doribt.serialization import encode, parameters_copy
from doribt.validation import DateLike

if TYPE_CHECKING:
    from doribt.reporting.result import BacktestResult

type Value = str | int | float | bool | None


def name_check(name: str) -> None:
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise ValueError("output names must be nonempty without surrounding whitespace")


def number(value: object) -> float | int | None:
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    if value is None:
        return None
    if type(value) not in (int, float):
        raise ValueError("research numeric values must be finite Python numbers or None")
    assert isinstance(value, (int, float))
    if not isfinite(value):
        raise ValueError("research numeric values must be finite")
    return value


@dataclass(frozen=True)
class Metric:
    value: float | int | None
    unit: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", number(self.value))

    def to_dict(self) -> dict[str, object]:
        return {"value": self.value, "unit": self.unit, "description": self.description}


@dataclass(frozen=True, kw_only=True)
class Series:
    sessions: Sequence[DateLike]
    values: Sequence[float | int | None]
    unit: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        sessions = time_points(self.sessions)
        values = tuple(number(value) for value in self.values)
        if len(sessions) != len(values):
            raise ValueError("series values must match its sessions")
        object.__setattr__(self, "sessions", sessions)
        object.__setattr__(self, "values", values)

    def to_dict(self) -> dict[str, object]:
        return {
            "sessions": list(self.sessions),
            "values": list(self.values),
            "unit": self.unit,
            "description": self.description,
        }


@dataclass(frozen=True, kw_only=True)
class Table:
    columns: Sequence[str]
    rows: Sequence[Mapping[str, Value]]
    description: str = ""
    _json: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        columns = tuple(self.columns)
        if not columns or len(set(columns)) != len(columns):
            raise ValueError("table columns must be nonempty and unique")
        for name in columns:
            name_check(name)
        copied = []
        for row in self.rows:
            if set(row) != set(columns):
                raise ValueError("each table row must have exactly the declared columns")
            for value in row.values():
                if value is not None and type(value) not in (str, bool, int, float):
                    raise ValueError("table cells must be JSON scalars")
            copied.append(parameters_copy(row))
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "rows", tuple(MappingProxyType(row) for row in copied))
        object.__setattr__(
            self,
            "_json",
            encode(
                {
                    "columns": list(columns),
                    "rows": copied,
                    "description": self.description,
                }
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self._json)
        return result


@dataclass(frozen=True, kw_only=True)
class ResearchOutput:
    metrics: Mapping[str, Metric] = field(default_factory=dict)
    series: Mapping[str, Series] = field(default_factory=dict)
    tables: Mapping[str, Table] = field(default_factory=dict)
    description: str = ""
    _json: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        names: set[str] = set()
        payload: dict[str, object] = {"description": self.description}
        for group, expected in (("metrics", Metric), ("series", Series), ("tables", Table)):
            items = dict(getattr(self, group))
            for name, item in items.items():
                name_check(name)
                if name in names or not isinstance(item, expected):
                    raise ValueError("output names must be unique and values match their kind")
                names.add(name)
            payload[group] = {name: item.to_dict() for name, item in items.items()}
            object.__setattr__(self, group, MappingProxyType(items))
        object.__setattr__(self, "_json", encode(payload))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self._json)
        return result

    def validate(self, sessions: Sequence[DateLike]) -> None:
        for series in self.series.values():
            if tuple(series.sessions) != tuple(sessions):
                raise ValueError("research series sessions must exactly match result sessions")


type Analyzer = Callable[["BacktestResult"], ResearchOutput]


class Recorder:
    def __init__(self, sessions: Sequence[DateLike]) -> None:
        self.sessions = sessions
        self.values: dict[str, list[float | int | None]] = {}
        self.written: set[tuple[int, str]] = set()

    def record(self, index: int, values: Mapping[str, float | int | None]) -> None:
        validated = {name: number(value) for name, value in values.items()}
        for name in validated:
            name_check(name)
            if (index, name) in self.written:
                raise ValueError(f"duplicate record at the same bar: {name}")
        for name, value in validated.items():
            if name not in self.values:
                self.values[name] = [None] * len(self.sessions)
            self.values[name][index] = value
            self.written.add((index, name))

    def output(self) -> ResearchOutput:
        return ResearchOutput(
            series={
                name: Series(sessions=self.sessions, values=values)
                for name, values in self.values.items()
            }
        )
