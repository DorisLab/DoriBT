"""Immutable public order history. All money fields are integer 1/10,000 yuan."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class Reason(StrEnum):
    NONE = "none"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"
    BUY_AT_UPPER_LIMIT = "buy_at_upper_limit"
    SELL_AT_LOWER_LIMIT = "sell_at_lower_limit"
    NO_VOLUME = "no_volume"
    INVALID_QUANTITY = "invalid_quantity"
    INSUFFICIENT_CASH = "insufficient_cash"
    INSUFFICIENT_SELLABLE = "insufficient_sellable"
    INSUFFICIENT_POSITION = "insufficient_position"
    PRICE_OUT_OF_RANGE = "price_out_of_range"
    PARTICIPATION_LIMIT = "participation_limit"
    LIMIT_PRICE = "limit_price"
    AUCTION = "auction"


REASONS = tuple(Reason)


@dataclass(frozen=True)
class Order:
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

    @property
    def commission(self) -> float:
        return self.commission_units / 10_000

    @property
    def stamp_duty(self) -> float:
        return self.stamp_duty_units / 10_000

    @property
    def transfer_fee(self) -> float:
        return self.transfer_fee_units / 10_000

    @property
    def events(self) -> tuple[str, ...]:
        if self.state:
            middle = ("partially_filled",) if self.filled and self.remaining else ()
            return ("created", "accepted", *middle, self.state)
        if self.reason == Reason.INVALID_QUANTITY:
            return ("created", "rejected")
        if self.filled == self.quantity:
            return ("created", "accepted", "filled")
        if self.filled:
            return ("created", "accepted", "partially_filled", "expired")
        return ("created", "accepted", "expired")

    @property
    def fees(self) -> float:
        return (self.commission_units + self.stamp_duty_units + self.transfer_fee_units) / 10_000

    @property
    def status(self) -> str:
        return self.events[-1]

    @property
    def remaining(self) -> int:
        return self.quantity - self.filled

    @property
    def price(self) -> float | None:
        if self.state and self.filled:
            return self.notional_units / abs(self.filled) / 10_000
        return self.price_units / 10_000 if self.filled else None


@dataclass(frozen=True)
class Fill:
    fill_id: int
    order_id: int
    intent_id: int
    session: date
    symbol: str
    quantity: int
    price_units: int
    commission_units: int
    stamp_duty_units: int
    transfer_fee_units: int
    timestamp: datetime | None = None
    reference_price_units: int | None = None

    @property
    def reference_price(self) -> float | None:
        """滑点前的 bar 开盘参考价；旧日线执行路径未记录时为 None。"""
        if self.reference_price_units is None:
            return None
        return self.reference_price_units / 10_000

    @property
    def slippage_cost_units(self) -> int | None:
        """已经计入成交金额的滑点价差成本，不应再次从现金扣除。"""
        if self.reference_price_units is None:
            return None
        return self.quantity * (self.price_units - self.reference_price_units)

    @property
    def slippage_cost(self) -> float | None:
        units = self.slippage_cost_units
        return None if units is None else units / 10_000

    @property
    def commission(self) -> float:
        return self.commission_units / 10_000

    @property
    def stamp_duty(self) -> float:
        return self.stamp_duty_units / 10_000

    @property
    def transfer_fee(self) -> float:
        return self.transfer_fee_units / 10_000

    @property
    def price(self) -> float:
        return self.price_units / 10_000

    @property
    def fees(self) -> float:
        return (self.commission_units + self.stamp_duty_units + self.transfer_fee_units) / 10_000

    @classmethod
    def from_order(cls, fill_id: int, order: Order) -> "Fill":
        return cls(
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
        )


@dataclass(frozen=True)
class TargetAdjustment:
    action_id: str
    session: date
    before: int
    after: int


@dataclass(frozen=True)
class IntentRecord:
    intent_id: int
    created: date
    symbol: str
    kind: str
    quantity: int
    status: str
    closed: date | None
    reason: str
    adjustments: tuple[TargetAdjustment, ...] = ()
