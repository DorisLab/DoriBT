"""先批量提取数值元数据，再完整创建独立成交记录。"""

from collections.abc import Callable

from doribt.accounting.orders import Fill
from doribt.accounting.records import record_factory
from doribt.kernels.broker_state import COLUMN, INTENT
from doribt.kernels.execution import OPEN, IntArray
from doribt.market.data import MarketData

fill_record: Callable[[tuple[object, ...]], Fill] = record_factory(Fill)


def materialize_fills(
    rows: IntArray,
    orders: IntArray,
    data: MarketData,
    market: IntArray,
    *,
    start: int = 0,
) -> list[Fill]:
    indices = rows[:, 0] - 1
    columns = orders[indices, COLUMN]
    intentions = orders[indices, INTENT].tolist()
    reference = market[rows[:, 1], columns, OPEN].tolist()
    sessions = tuple(data.sessions[data.day_index(index)] for index in range(len(data.timeline)))
    timeline = data.timeline if data.clock else (None,) * len(data.timeline)
    result = []
    for identifier, (row, column, intent, price_reference) in enumerate(
        zip(rows.tolist(), columns.tolist(), intentions, reference, strict=True),
        start + 1,
    ):
        order_id, index, quantity, price, commission, stamp, transfer = row
        result.append(
            fill_record(
                (
                    identifier,
                    order_id,
                    intent,
                    sessions[index],
                    data.symbols[column],
                    quantity,
                    price,
                    commission,
                    stamp,
                    transfer,
                    timeline[index],
                    price_reference,
                )
            )
        )
    return result
