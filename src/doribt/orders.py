"""Immutable public order history. All money fields are integer 1/10,000 yuan."""

from dataclasses import dataclass
from datetime import date
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
