"""在分配账户和逐栏状态前，选择预计算目标的执行路径。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np

from doribt.accounting.costs import Costs
from doribt.kernels.compiled import CompiledData, PreparedData
from doribt.kernels.execution import executor
from doribt.market.data import MarketData
from doribt.provenance import RunInfo
from doribt.reporting.result import BacktestResult
from doribt.runtime.context import Context
from doribt.runtime.execution_audit import jit_enabled
from doribt.runtime.slippage import BarExecution
from doribt.runtime.targets import PositionTargets, WeightTargets


class RunDriver(Protocol):
    def execute(self, strategy: Callable[[Context], None], info: RunInfo) -> BacktestResult: ...


@dataclass(frozen=True)
class TargetCandidate:
    data: MarketData
    compiled: CompiledData
    backend: str
    precomputed_targets: PositionTargets | WeightTargets


class CompiledRun:
    """编译循环拥有账户输出；此处只持有输入和无公司行动的补充结果。"""

    def __init__(
        self,
        prepared: PreparedData,
        initial_cash: int,
        costs: Costs,
        backend: str,
        execution: BarExecution,
        targets: PositionTargets | WeightTargets,
        plan: Literal["daily_targets", "compiled_schedule"],
    ) -> None:
        executor(backend)  # 保留显式请求未安装后端时的错误。
        self.data, self.compiled = prepared.data, prepared.compiled
        self.initial_cash, self.costs, self.backend = initial_cash, costs.compile(), backend
        self.precomputed_targets, self.plan = targets, plan
        self.columns, self.intrabar = prepared.columns, prepared.intrabar
        self.execution_config = execution.compile()
        bars, width = len(self.data.timeline), len(self.data.symbols)
        self.pending_shares = np.zeros((bars, width), dtype=np.int64)
        self.receivable = np.zeros(bars, dtype=np.int64)
        self.tax_payable = np.zeros(bars, dtype=np.int64)
        if plan == "daily_targets":
            self.reserved_cash = np.zeros(bars, dtype=np.int64)
            self.reserved_shares = np.zeros((bars, width), dtype=np.int64)

    def execute(self, strategy: Callable[[Context], None], info: RunInfo) -> BacktestResult:
        if self.plan == "daily_targets":
            from doribt.runtime.compiled_targets import execute
        else:
            from doribt.runtime.compiled_schedule import execute
        return execute(self, info)


def target_run(
    prepared: PreparedData,
    initial_cash: int,
    costs: Costs,
    backend: str,
    execution: BarExecution,
    targets: PositionTargets | WeightTargets,
) -> RunDriver:
    from doribt.runtime.compiled_schedule import eligible as eligible_schedule
    from doribt.runtime.compiled_targets import eligible

    executor(backend)
    candidate = TargetCandidate(prepared.data, prepared.compiled, backend, targets)
    plan: Literal["daily_targets", "compiled_schedule"] | None = None
    if jit_enabled(backend) and eligible_schedule(candidate):
        plan = "compiled_schedule"
    elif jit_enabled(backend) and eligible(candidate):
        plan = "daily_targets"
    if plan is not None:
        return CompiledRun(prepared, initial_cash, costs, backend, execution, targets, plan)
    from doribt.runtime.scheduled import ScheduledRun

    return ScheduledRun(prepared, initial_cash, costs, backend, execution, targets)
