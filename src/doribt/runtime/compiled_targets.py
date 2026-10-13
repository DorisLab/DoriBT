"""严格限定的日线目标编译路径；完整审计记录在计时内物化。"""

from typing import TYPE_CHECKING, cast

import numpy as np

from doribt.accounting.orders import REASONS, Fill, IntentRecord, Order
from doribt.accounting.taxes import TaxLotRecord
from doribt.kernels.execution import OPEN, IntArray
from doribt.kernels.target_loop import compiled_targets
from doribt.provenance import RunInfo
from doribt.reporting.result import BacktestResult
from doribt.runtime.targets import PositionTargets

if TYPE_CHECKING:
    from doribt.runtime.execution_plan import CompiledRun, TargetCandidate


def eligible(run: "TargetCandidate") -> bool:
    return (
        run.backend == "numba"
        and type(run.precomputed_targets) is PositionTargets
        and run.data.clock is None
        and not run.data.actions
    )


def materialize_orders(rows: IntArray, run: "CompiledRun") -> tuple[Order, ...]:
    sessions, symbols = run.data.sessions, run.data.symbols
    states = ("rejected", "filled", "expired")
    return tuple(
        Order(
            index + 1,
            intent + 1,
            sessions[session],
            symbols[column],
            quantity,
            filled,
            price,
            commission,
            stamp,
            transfer,
            REASONS[reason],
            sessions[created],
            sessions[session],
            states[state],
            abs(filled) * price,
            "day",
        )
        for index, (
            intent,
            column,
            created,
            session,
            quantity,
            filled,
            price,
            commission,
            stamp,
            transfer,
            reason,
            state,
        ) in enumerate(rows.tolist())
    )


def materialize_intents(rows: IntArray, run: "CompiledRun") -> tuple[IntentRecord, ...]:
    statuses = ("active", "fulfilled", "cancelled", "unexecuted")
    reasons = ("", "target_below_minimum", "target_replaced", "end_of_data")
    return tuple(
        IntentRecord(
            index + 1,
            run.data.sessions[created],
            run.data.symbols[column],
            "target",
            quantity,
            statuses[status],
            run.data.sessions[closed],
            reasons[reason],
        )
        for index, (column, created, quantity, closed, status, reason) in enumerate(rows.tolist())
    )


def materialize_fills(
    orders: tuple[Order, ...],
    rows: IntArray,
    indices: IntArray,
    run: "CompiledRun",
) -> tuple[Fill, ...]:
    result: list[Fill] = []
    reference_prices = run.compiled.market[rows[indices, 3], rows[indices, 1], OPEN].tolist()
    for fill_id, (order_id, reference_price) in enumerate(
        zip(indices.tolist(), reference_prices, strict=True), 1
    ):
        order = orders[order_id]
        result.append(
            Fill(
                fill_id,
                order.order_id,
                order.intent_id,
                order.session,
                order.symbol,
                order.filled,
                order.price_units,
                order.commission_units,
                order.stamp_duty_units,
                order.transfer_fee_units,
                reference_price_units=reference_price,
            )
        )
    return tuple(result)


def execute(run: "CompiledRun", info: RunInfo) -> BacktestResult:
    target = cast(PositionTargets, run.precomputed_targets)
    columns = np.array([run.columns[symbol] for symbol in target.quantities], dtype=np.int64)
    values = (
        np.array(tuple(target.quantities.values()), dtype=np.int64)
        .reshape(len(columns), len(run.data.sessions))
        .T.copy()
    )
    equity, cash, holdings, sellable, rows, intentions, lots, fill_indices = compiled_targets()(
        values,
        columns,
        run.compiled.market,
        run.compiled.closes,
        run.intrabar,
        run.compiled.settlement,
        run.costs,
        run.execution_config,
        run.initial_cash,
    )
    orders = materialize_orders(rows, run)
    intents = materialize_intents(intentions, run)
    fills = materialize_fills(orders, rows, fill_indices, run)
    tax_lots = tuple(
        TaxLotRecord(index + 1, run.data.symbols[column], run.data.sessions[acquired], quantity, ())
        for index, (column, acquired, quantity, _) in enumerate(lots.tolist())
        if quantity
    )
    for array in (
        equity,
        cash,
        holdings,
        sellable,
        run.pending_shares,
        run.receivable,
        run.tax_payable,
        run.reserved_cash,
        run.reserved_shares,
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
        reserved_cash_units=run.reserved_cash,
        reserved_shares=run.reserved_shares,
    )
