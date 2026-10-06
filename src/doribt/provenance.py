"""Run facts and hashes without collecting environment secrets or copying strategy code."""

import hashlib
import inspect
import json
import platform
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

from .context import Context
from .costs import Costs
from .data import MarketData
from .slippage import BarExecution
from .targets import PositionTargets, WeightTargets
from .taxes import TAX_POLICY

MODEL = "daily-fixed-shares-next-open-v1"


def _encode(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"unsupported serialized value: {type(value).__name__}")


def encode(value: object) -> str:
    return json.dumps(value, default=_encode, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def _json_parameter(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("parameter object keys must be strings")
            _json_parameter(item)
    elif isinstance(value, list):
        for item in value:
            _json_parameter(item)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError("parameters must contain only JSON objects, lists and scalars")


def parameters_copy(parameters: Mapping[str, object] | None) -> dict[str, Any]:
    values = dict(parameters or {})
    _json_parameter(values)
    # Round trip validates finite numbers and snapshots nested mutable values.
    copied: dict[str, Any] = json.loads(encode(values))
    return copied


def bind_strategy(
    strategy: Callable[..., None], parameters: dict[str, Any]
) -> Callable[[Context], None]:
    try:
        inspect.signature(strategy).bind(None, **parameters)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"strategy must accept context and the supplied parameters: {error}"
        ) from error

    def callback(context: Context) -> None:
        strategy(context, **parameters)

    return callback


def _strategy_info(strategy: Callable[..., None]) -> dict[str, object]:
    inputs: dict[str, object]
    if type(strategy) is PositionTargets:
        inputs = {"sessions": list(strategy.sessions), "quantities": dict(strategy.quantities)}
        return {"kind": "position_targets", "input_sha256": digest(inputs), "inputs": inputs}
    if type(strategy) is WeightTargets:
        inputs = {
            "sessions": list(strategy.sessions),
            "weights": dict(strategy.weights),
            "rebalance": strategy.rebalance,
        }
        return {"kind": "weight_targets", "input_sha256": digest(inputs), "inputs": inputs}
    identity = strategy if inspect.isfunction(strategy) else type(strategy)
    try:
        source_hash = hashlib.sha256(inspect.getsource(identity).encode()).hexdigest()
    except (OSError, TypeError):
        source_hash = None
    return {
        "kind": "callback",
        "module": identity.__module__,
        "name": identity.__qualname__,
        "source_sha256": source_hash,
        "external_state": "not_captured",
    }


def _versions(backend: str) -> dict[str, str]:
    versions = {"python": platform.python_version(), "platform": platform.platform()}
    packages = ["doribt", "numpy"] + (["numba", "llvmlite"] if backend == "numba" else [])
    for package in packages:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "not_installed"
    return versions


@dataclass(frozen=True)
class RunInfo:
    """Immutable canonical JSON; ``to_dict`` returns a fresh editable copy."""

    json: str

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = json.loads(self.json)
        return value

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.json.encode("utf-8")).hexdigest()


def data_info(data: MarketData) -> dict[str, object]:
    rules, actions = [asdict(p) for p in data.rules.periods], [asdict(a) for a in data.actions]
    return {
        "fingerprint": data.fingerprint,
        "source": data.source,
        "instruments": [asdict(i) for i in data.instruments],
        "sessions": list(data.sessions),
        "frequency": data.clock.frequency if data.clock else "1d",
        "timestamps": list(data.timeline) if data.clock else None,
        "rules": rules,
        "actions": actions,
        "rules_sha256": digest(rules),
        "actions_sha256": digest(actions),
        "adjustments": [asdict(item) for item in data.adjustments],
    }


def encode_run(payload: dict[str, object], fragments: dict[str, str]) -> str:
    """Join canonical immutable JSON fragments without re-encoding every timestamp.

    Only data/target snapshots are cached; code hashes, parameters and dependency
    versions are still captured for each run. The result remains ordinary canonical
    JSON, byte-identical to encode() on the complete object.
    """
    entries = {key: encode(value) for key, value in payload.items()} | fragments
    return "{" + ", ".join(encode(key) + ": " + entries[key] for key in sorted(entries)) + "}"


def run_info(
    data: MarketData,
    initial_cash: int,
    costs: Costs,
    strategy: Callable[..., None],
    parameters: dict[str, Any],
    backend: str,
    execution: BarExecution | None = None,
    *,
    data_json: str | None = None,
) -> RunInfo:
    root = Path(__file__).parent
    code = {
        str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(root.rglob("*.py"))
    }
    strategy_json = (
        cast(PositionTargets | WeightTargets, strategy)._provenance_json
        if type(strategy) in (PositionTargets, WeightTargets)
        else encode(_strategy_info(strategy))
    )
    payload: dict[str, object] = {
        "schema": "doribt.run/1",
        "model": MODEL if execution is None else "bar-partial-next-open-v1",
        "execution": None
        if execution is None
        else {
            "participation_ppm": int(execution.compile()[0]),
            "slippage": type(execution.slippage).__name__,
            "parameters": asdict(execution.slippage),
            "quantity_unit": "shares",
            "fill_known": "bar_end",
        },
        "backend": backend,
        "execution_path": "scheduled_segments"
        if execution is not None and type(strategy) in (PositionTargets, WeightTargets)
        else "bar_callbacks",
        "initial_cash_units": initial_cash,
        "costs": dict(
            zip(
                ("commission_ppm", "minimum_commission_units", "slippage_ticks"),
                map(int, costs.compile()),
                strict=True,
            )
        ),
        "tax_policy": TAX_POLICY,
        "parameters": parameters,
        "versions": _versions(backend),
        "engine_sha256": digest(code),
        "assumptions": {
            "decision": "close",
            "execution": "next_supplied_open"
            if execution is None
            else "next_bar_open_reference_confirmed_at_bar_end",
            "quantity": "fixed_at_decision",
            "allocation": "sells_then_symbol_order"
            if execution is None
            else "sells_then_submission_order",
            "prices": "raw",
            "external_cash_flows": False,
            "final_liquidation": False,
            "order_lifetime": "one_open_attempt"
            if execution is None
            else "explicit_next_bar_or_day",
        },
    }
    return RunInfo(
        encode_run(
            payload,
            {
                "data": data_json if data_json is not None else encode(data_info(data)),
                "strategy": strategy_json,
            },
        )
    )
