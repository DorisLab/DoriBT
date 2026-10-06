"""Declarative strategy parameters, validated before any callback executes."""

import keyword
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from types import MappingProxyType
from typing import Literal

type Scalar = str | int | float | bool


@dataclass(frozen=True, kw_only=True)
class Parameter:
    type: Literal["int", "float", "str", "bool"]
    default: Scalar
    label: str = ""
    description: str = ""
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    choices: tuple[Scalar, ...] = ()

    def __post_init__(self) -> None:
        if self.type not in {"int", "float", "str", "bool"}:
            raise ValueError("unsupported parameter type")
        object.__setattr__(self, "choices", tuple(self.choices))
        self._bounds()
        for choice in self.choices:
            self.validate(choice)
        self.validate(self.default)

    def _bounds(self) -> None:
        for name in ("minimum", "maximum", "step"):
            value = getattr(self, name)
            if value is not None:
                if self.type not in {"int", "float"} or isinstance(value, bool):
                    raise ValueError("bounds and step require numeric parameters")
                if not isinstance(value, (int, float)) or not isfinite(value):
                    raise ValueError("bounds and step must be finite numbers")
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("minimum must not exceed maximum")
        if self.step is not None and self.step <= 0:
            raise ValueError("step must be positive")

    def validate(self, value: object) -> Scalar:
        types = {"int": (int,), "float": (int, float), "str": (str,), "bool": (bool,)}
        if type(value) not in types[self.type]:
            raise ValueError(f"expected parameter type {self.type}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            self._number(value)
        if self.choices and value not in self.choices:
            raise ValueError("value is not a declared choice")
        assert isinstance(value, (str, int, float, bool))
        return value

    def _number(self, value: int | float) -> None:
        if not isfinite(value):
            raise ValueError("parameter must be finite")
        if self.minimum is not None and value < self.minimum:
            raise ValueError("parameter is below minimum")
        if self.maximum is not None and value > self.maximum:
            raise ValueError("parameter exceeds maximum")
        if self.step is not None:
            origin = self.minimum if self.minimum is not None else 0
            if (Decimal(str(value)) - Decimal(str(origin))) % Decimal(str(self.step)):
                raise ValueError("parameter does not align with step from minimum (or zero)")

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "type": {"int": "integer", "float": "number", "str": "string", "bool": "boolean"}[
                self.type
            ],
            "default": self.default,
            "title": self.label,
            "description": self.description,
            "unit": self.unit,
        }
        for key in ("minimum", "maximum", "step"):
            if getattr(self, key) is not None:
                result[key] = getattr(self, key)
        if self.choices:
            result["enum"] = list(self.choices)
        return result


@dataclass(frozen=True)
class ParameterSet:
    parameters: Mapping[str, Parameter]

    def __post_init__(self) -> None:
        for name, parameter in self.parameters.items():
            if not isinstance(name, str) or not name.isidentifier() or keyword.iskeyword(name):
                raise ValueError("parameter names must be Python identifiers")
            if not isinstance(parameter, Parameter):
                raise ValueError("parameter declarations must be Parameter objects")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))

    def resolve(self, values: Mapping[str, object] | None = None) -> dict[str, object]:
        supplied = dict(values or {})
        if any(not isinstance(name, str) for name in supplied):
            raise ValueError("parameter names must be strings")
        unknown = supplied.keys() - self.parameters.keys()
        if unknown:
            raise ValueError(f"unknown parameters: {sorted(unknown)}")
        result: dict[str, object] = {}
        for name, spec in self.parameters.items():
            try:
                result[name] = spec.validate(supplied.get(name, spec.default))
            except ValueError as error:
                raise ValueError(f"parameter {name}: {error}") from error
        return result

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {name: spec.to_dict() for name, spec in self.parameters.items()},
        }
