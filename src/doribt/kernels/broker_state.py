"""通用订单数组布局；日线、分钟和回调共享生命周期状态。"""

from collections.abc import Callable

from doribt.accounting.orders import REASONS, Order
from doribt.accounting.records import record_factory
from doribt.kernels.execution import IntArray
from doribt.market.data import MarketData
from doribt.runtime.order_state import OrderState

order_record: Callable[[tuple[object, ...]], Order] = record_factory(Order)


# 前六列保持撮合器输入布局，其他列记录完整委托生命周期。
COLUMN, SUBMITTED, ACTIVATION, SPEND, BUYING, QUANTITY, INTENT = range(6, 13)
FILLED, PRICE, STAMP_PAID, TRANSFER_PAID, REASON, SESSION, UPDATED = range(13, 20)
STATE, VALID, CEILING = range(20, 23)
WIDTH = 23
ACCEPTED, REJECTED, PARTIAL, COMPLETE, EXPIRED, CANCELLED, UNEXECUTED = range(7)
STATES = (
    "accepted",
    "rejected",
    "partially_filled",
    "filled",
    "expired",
    "cancelled",
    "unexecuted",
)


def restore_order(row: IntArray, order: OrderState, data: MarketData) -> None:
    order.session = data.sessions[data.day_index(int(row[SESSION]))]
    order.updated_at = data.timeline[int(row[UPDATED])]
    order.state = STATES[int(row[STATE])]
    order.filled = int(row[FILLED])
    order.price_units = int(row[PRICE])
    order.notional_units = int(row[1])
    order.commission_units = int(row[2])
    order.stamp_duty_units = int(row[STAMP_PAID])
    order.transfer_fee_units = int(row[TRANSFER_PAID])
    order.reason = REASONS[int(row[REASON])]
    order.frozen_cash_units = int(row[3])
    order.frozen_quantity = int(row[4])


def order_snapshotter(data: MarketData) -> Callable[[list[int], int], Order]:
    sessions = tuple(data.sessions[data.day_index(index)] for index in range(len(data.timeline)))
    timeline, symbols = data.timeline, data.symbols

    def snapshot(row: list[int], order_id: int) -> Order:
        return order_record(
            (
                order_id,
                row[INTENT],
                sessions[row[SESSION]],
                symbols[row[COLUMN]],
                row[QUANTITY],
                row[FILLED],
                row[PRICE],
                row[2],
                row[STAMP_PAID],
                row[TRANSFER_PAID],
                REASONS[row[REASON]],
                timeline[row[SUBMITTED]],
                timeline[row[UPDATED]],
                STATES[row[STATE]],
                row[1],
                "day" if row[VALID] else "next_bar",
                row[5],
                row[3],
                row[4],
                None if row[CEILING] < 0 else row[CEILING],
            )
        )

    return snapshot
