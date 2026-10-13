"""公开实际执行计划；保留旧 execution_path 的执行族含义。"""

from collections.abc import Callable

from doribt.market.data import MarketData
from doribt.runtime.slippage import BarExecution
from doribt.runtime.targets import PositionTargets, WeightTargets


def jit_enabled(backend: str) -> bool:
    if backend != "numba":
        return False
    from numba import config

    # Numba 在运行时生成此属性，官方包未提供对应类型声明。
    return not bool(config.DISABLE_JIT)  # type: ignore[attr-defined]


def execution_audit(
    driver: object,
    strategy: Callable[..., None],
    backend: str,
    data: MarketData,
    execution: BarExecution | None,
) -> dict[str, object]:
    from doribt.runtime.execution_plan import CompiledRun
    from doribt.runtime.scheduled import ScheduledRun

    jit = jit_enabled(backend)
    reasons: list[dict[str, object]] = []
    plan = "bar_callbacks"
    if isinstance(driver, CompiledRun):
        plan = "compiled_targets"
    elif isinstance(driver, ScheduledRun):
        plan = "scheduled_segments"
    if plan != "compiled_targets":
        reasons = fallback_reasons(strategy, backend, jit, data, execution)
    return {
        "schema": "doribt.execution-plan/1",
        "requested_backend": backend,
        "actual_backend": "numba" if jit else "python",
        "jit_enabled": jit,
        "plan": plan,
        "compiled_scope": "targets_and_matching"
        if plan == "compiled_targets"
        else "matching"
        if jit
        else "none",
        "fallback_reasons": reasons,
    }


def fallback_reasons(
    strategy: Callable[..., None],
    backend: str,
    jit: bool,
    data: MarketData,
    execution: BarExecution | None,
) -> list[dict[str, object]]:
    reasons: list[dict[str, object]] = []
    for condition, code, detail in (
        (backend != "numba", "python_backend", "请求 Python 后端。"),
        (backend == "numba" and not jit, "jit_disabled", "Numba JIT 已禁用。"),
        (execution is None, "legacy_execution", "旧日线执行模型使用逐 bar 生命周期。"),
        (bool(data.actions), "corporate_actions", "公司行动使用兼容生命周期。"),
        (
            type(strategy) not in (PositionTargets, WeightTargets),
            "custom_target"
            if isinstance(strategy, (PositionTargets, WeightTargets))
            else "callback",
            "用户回调或目标子类保留 Python 调用。",
        ),
    ):
        if condition:
            reasons.append({"code": code, "detail": detail})
    return reasons or [{"code": "unsupported_plan", "detail": "执行器选择了兼容路径。"}]
