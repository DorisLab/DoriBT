"""One explicit runtime configuration for daily and minute research."""

from dataclasses import dataclass, field
from typing import Literal

from doribt.accounting.costs import Costs
from doribt.research.parameters import Parameter, ParameterSet
from doribt.runtime.slippage import BarExecution, FixedBps, FixedTicks, VolumeImpact
from doribt.validation import Number, amount


@dataclass(frozen=True, kw_only=True)
class RunConfig:
    initial_cash: Number = 100_000
    costs: Costs = field(default_factory=Costs)
    execution: BarExecution = field(default_factory=BarExecution)
    backend: Literal["python", "numba"] = "python"

    def __post_init__(self) -> None:
        if not amount(self.initial_cash, "initial_cash"):
            raise ValueError("initial_cash must be positive")
        if not isinstance(self.costs, Costs) or not isinstance(self.execution, BarExecution):
            raise ValueError("config requires Costs and BarExecution")
        if self.costs.slippage_ticks:
            raise ValueError("configure slippage through execution, not Costs.slippage_ticks")
        if self.backend not in {"python", "numba"}:
            raise ValueError("backend must be python or numba")

    def to_dict(self) -> dict[str, object]:
        commission, minimum, _ = map(int, self.costs.compile())
        slip = self.execution.slippage
        if isinstance(slip, FixedTicks):
            kind, size = "ticks", float(slip.ticks)
        elif isinstance(slip, FixedBps):
            kind, size = "bps", float(slip.bps)
        else:
            kind, size = "volume_impact", float(slip.coefficient)
        return {
            "initial_cash": amount(self.initial_cash, "initial_cash") / 10_000,
            "commission": commission / 1_000_000,
            "minimum_commission": minimum / 10_000,
            "participation": float(self.execution.participation),
            "slippage_kind": kind,
            "slippage_value": size,
            "backend": self.backend,
        }

    @staticmethod
    def schema() -> ParameterSet:
        return ParameterSet(
            {
                "initial_cash": Parameter(
                    type="float",
                    default=100_000,
                    minimum=0.0001,
                    maximum=10_000_000_000,
                    step=0.0001,
                    unit="CNY",
                    label="初始资金",
                ),
                "commission": Parameter(
                    type="float",
                    default=0.0003,
                    minimum=0,
                    maximum=1,
                    step=0.000001,
                    unit="ratio",
                    label="佣金比例",
                ),
                "minimum_commission": Parameter(
                    type="float",
                    default=5,
                    minimum=0,
                    maximum=10_000_000_000,
                    step=0.01,
                    unit="CNY",
                    label="最低佣金",
                ),
                "participation": Parameter(
                    type="float",
                    default=0.05,
                    minimum=0.000001,
                    maximum=1,
                    step=0.000001,
                    unit="ratio",
                    label="成交比例",
                ),
                "slippage_kind": Parameter(
                    type="str",
                    default="ticks",
                    choices=("ticks", "bps", "volume_impact"),
                    label="滑点模型",
                ),
                "slippage_value": Parameter(
                    type="float",
                    default=0,
                    minimum=0,
                    label="滑点数值",
                    description=(
                        "ticks: integer ticks; bps: basis points; volume_impact: ratio coefficient"
                    ),
                ),
                "backend": Parameter(type="str", default="python", choices=("python", "numba")),
            }
        )

    @classmethod
    def from_dict(cls, values: dict[str, object]) -> "RunConfig":
        resolved = cls.schema().resolve(values)
        size = float(str(resolved["slippage_value"]))
        kind = resolved["slippage_kind"]
        if kind == "ticks":
            if not size.is_integer():
                raise ValueError("tick slippage must be an integer")
            slip: FixedTicks | FixedBps | VolumeImpact = FixedTicks(int(size))
        elif kind == "bps":
            slip = FixedBps(size)
        else:
            slip = VolumeImpact(size)
        return cls(
            initial_cash=str(resolved["initial_cash"]),
            costs=Costs(
                commission=str(resolved["commission"]),
                minimum_commission=str(resolved["minimum_commission"]),
            ),
            execution=BarExecution(participation=str(resolved["participation"]), slippage=slip),
            backend="numba" if resolved["backend"] == "numba" else "python",
        )
