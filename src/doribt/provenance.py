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
from typing import Any

from .context import Context
from .costs import Costs
from .data import MarketData
from .targets import WeightTargets
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
    if isinstance(strategy, WeightTargets):
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


def run_info(
    data: MarketData,
    initial_cash: int,
    costs: Costs,
    strategy: Callable[..., None],
    parameters: dict[str, Any],
    backend: str,
) -> RunInfo:
    root = Path(__file__).parent
    code = {
        str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(root.rglob("*.py"))
    }
    rules, actions = [asdict(p) for p in data.rules.periods], [asdict(a) for a in data.actions]
    payload = {
        "schema": "doribt.run/1",
        "model": MODEL,
        "backend": backend,
        "initial_cash_units": initial_cash,
        "costs": dict(
            zip(
                ("commission_ppm", "minimum_commission_units", "slippage_ticks"),
                map(int, costs.compile()),
                strict=True,
            )
        ),
        "tax_policy": TAX_POLICY,
        "strategy": _strategy_info(strategy),
        "parameters": parameters,
        "data": {
            "fingerprint": data.fingerprint,
            "source": data.source,
            "instruments": [asdict(i) for i in data.instruments],
            "sessions": list(data.sessions),
            "rules": rules,
            "actions": actions,
            "rules_sha256": digest(rules),
            "actions_sha256": digest(actions),
        },
        "versions": _versions(backend),
        "engine_sha256": digest(code),
        "assumptions": {
            "decision": "close",
            "execution": "next_supplied_open",
            "quantity": "fixed_at_decision",
            "allocation": "sells_then_symbol_order",
            "prices": "raw",
            "external_cash_flows": False,
            "final_liquidation": False,
            "order_lifetime": "one_open_attempt",
        },
    }
    return RunInfo(encode(payload))
