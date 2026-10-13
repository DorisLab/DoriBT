"""预计算分钟意图的数组执行与完整结果记录物化。"""

from collections.abc import Callable
from typing import TYPE_CHECKING, NoReturn, cast

import numpy as np

from doribt.accounting.orders import IntentRecord
from doribt.accounting.records import record_factory
from doribt.accounting.taxes import TaxLotRecord
from doribt.kernels.broker_state import order_snapshotter
from doribt.kernels.execution import IntArray
from doribt.kernels.scheduled_loop import compiled_schedule
from doribt.provenance import RunInfo
from doribt.reporting.result import BacktestResult
from doribt.runtime import native_records
from doribt.runtime.record_materialization import materialize_fills
from doribt.runtime.targets import PositionTargets, WeightTargets

intent_record: Callable[[tuple[object, ...]], IntentRecord] = record_factory(IntentRecord)
tax_lot_record: Callable[[tuple[object, ...]], TaxLotRecord] = record_factory(TaxLotRecord)


if TYPE_CHECKING:
    from doribt.runtime.execution_plan import CompiledRun, TargetCandidate


def eligible(run: "TargetCandidate") -> bool:
    if run.backend != "numba" or run.data.actions:
        return False
    if type(run.precomputed_targets) is WeightTargets:
        return True
    return type(run.precomputed_targets) is PositionTargets and run.data.clock is not None


def materialize_intents(rows: IntArray, run: "CompiledRun") -> tuple[IntentRecord, ...]:
    statuses = ("active", "fulfilled", "cancelled", "unexecuted")
    reasons = ("", "target_below_minimum", "target_replaced", "end_of_data")
    sizing = ("quantity", "close", "execution")
    data = run.data
    sessions = tuple(data.sessions[data.day_index(i)] for i in range(len(data.timeline)))
    return tuple(
        intent_record(
            (
                identifier + 1,
                sessions[created],
                data.symbols[column],
                "target",
                None if mode == 2 and sized < 0 else quantity,
                statuses[state],
                sessions[closed],
                reasons[reason],
                (),
                None if weight < 0 else weight,
                sizing[mode],
                None if sized < 0 else data.timeline[sized],
            )
        )
        for identifier, (
            column,
            created,
            quantity,
            closed,
            state,
            reason,
            weight,
            mode,
            sized,
        ) in enumerate(rows.tolist())
    )


def execute(run: "CompiledRun", info: RunInfo) -> BacktestResult:
    values, columns, options = target_arrays(run)
    days = np.array(
        [run.data.day_index(index) for index in range(len(run.data.timeline))], dtype=np.int64
    )
    ordinals = np.array([session.toordinal() for session in run.data.sessions], dtype=np.int64)
    try:
        arrays = compiled_schedule()(
            values,
            columns,
            run.compiled.market,
            run.compiled.closes,
            run.intrabar,
            run.compiled.settlement,
            run.costs,
            run.execution_config,
            days,
            ordinals,
            run.compiled.sizing_rules,
            run.initial_cash,
            options,
        )
    except ValueError as error:
        restore_error(error, run)
    equity, cash, holdings, sellable, rows, intentions, lots, fill_rows, frozen, reserved = arrays
    if native_records.available():
        orders, intents, fills, tax_lots = native_records.materialize(
            rows, intentions, lots, fill_rows, run.data, run.compiled.market
        )
    else:
        snapshot = order_snapshotter(run.data)
        orders = tuple(snapshot(row, identifier) for identifier, row in enumerate(rows.tolist(), 1))
        intents = materialize_intents(intentions, run)
        fills = tuple(materialize_fills(fill_rows, rows, run.data, run.compiled.market))
        tax_lots = tuple(
            tax_lot_record(
                (
                    identifier + 1,
                    run.data.symbols[column],
                    run.data.sessions[acquired],
                    quantity,
                    (),
                )
            )
            for identifier, (column, acquired, quantity, _) in enumerate(lots.tolist())
            if quantity
        )
    for array in (
        equity,
        cash,
        holdings,
        sellable,
        frozen,
        reserved,
        run.pending_shares,
        run.receivable,
        run.tax_payable,
    ):
        array.setflags(write=False)
    return BacktestResult(
        run.data.timeline,
        run.data.symbols,
        run.initial_cash / 10_000,
        equity,
        cash,
        holdings,
        sellable,
        orders,
        intents,
        run.backend,
        run.data.fingerprint,
        run.pending_shares,
        run.receivable,
        run.tax_payable,
        (),
        (),
        (),
        tax_lots,
        (),
        run.compiled.closes,
        info,
        executions=fills,
        reserved_cash_units=frozen,
        reserved_shares=reserved,
    )


def target_arrays(run: "CompiledRun") -> tuple[IntArray, IntArray, IntArray]:
    target = run.precomputed_targets
    if type(target) is PositionTargets:
        columns = np.array([run.columns[symbol] for symbol in target.quantities], dtype=np.int64)
        values = (
            np.array(tuple(target.quantities.values()), dtype=np.int64)
            .reshape(len(columns), len(run.data.timeline))
            .T.copy()
        )
        return values, columns, np.array([0, 0], dtype=np.int64)
    weights = cast(WeightTargets, target)
    columns = np.arange(len(run.data.symbols), dtype=np.int64)
    values = np.zeros((len(run.data.timeline), len(columns)), dtype=np.int64)
    for column, symbol in enumerate(run.data.symbols):
        if symbol in weights.weights:
            values[:, column] = np.rint(np.asarray(weights.weights[symbol]) * 1_000_000).astype(
                np.int64
            )
    options = np.array(
        [1 if weights.sizing == "close" else 2, int(weights.rebalance)], dtype=np.int64
    )
    return values, columns, options


def restore_error(error: ValueError, run: "CompiledRun") -> NoReturn:
    if len(error.args) != 5 or error.args[0] != "weight_sizing":
        raise error
    _, index, mode, code, column = error.args
    original: ValueError | OverflowError
    original = (
        ValueError("cannot size a target without a current valuation")
        if code == 1
        else OverflowError("target quantity exceeds supported bounds")
    )
    if code == 3:
        session = run.data.sessions[run.data.day_index(index)]
        original = ValueError(
            f"missing historical rule for {run.data.symbols[column]} on {session}"
        )
    if mode == 1:
        session = run.data.timeline[index]
        raise RuntimeError(f"strategy failed at close on {session}: {original}") from original
    raise original from None
