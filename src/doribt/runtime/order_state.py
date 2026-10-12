"""内部可变订单状态；对外仅暴露独立、不可变的 Order 快照。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from doribt.accounting.orders import Order, Reason
from doribt.accounting.records import record_factory

order_record: Callable[[tuple[object, ...]], Order] = record_factory(Order)


@dataclass(slots=True)
class OrderState:
    order_id: int
    intent_id: int
    session: date
    symbol: str
    quantity: int
    filled: int
    price_units: int
    commission_units: int
    stamp_duty_units: int
    transfer_fee_units: int
    reason: Reason
    created_at: date | None = None
    updated_at: date | None = None
    state: str = ""
    notional_units: int = 0
    valid_for: str = "next_bar"
    limit_units: int = 0
    frozen_cash_units: int = 0
    frozen_quantity: int = 0
    max_spend_units: int | None = None

    def snapshot(self) -> Order:
        return order_record(
            (
                self.order_id,
                self.intent_id,
                self.session,
                self.symbol,
                self.quantity,
                self.filled,
                self.price_units,
                self.commission_units,
                self.stamp_duty_units,
                self.transfer_fee_units,
                self.reason,
                self.created_at,
                self.updated_at,
                self.state,
                self.notional_units,
                self.valid_for,
                self.limit_units,
                self.frozen_cash_units,
                self.frozen_quantity,
                self.max_spend_units,
            )
        )

    @property
    def status(self) -> str:
        return self.state
