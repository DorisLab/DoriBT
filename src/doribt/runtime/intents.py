"""Pending targets are distinct from their one-session child orders."""

from dataclasses import dataclass, field
from datetime import date

from doribt.accounting.orders import IntentRecord, TargetAdjustment


@dataclass
class Intent:
    intent_id: int
    created: date
    symbol: str
    kind: str
    quantity: int
    status: str = "active"
    closed: date | None = None
    reason: str = ""
    adjustments: list[TargetAdjustment] = field(default_factory=list)
    weight_ppm: int | None = None
    sizing: str = "quantity"
    sized_at: date | None = None

    @property
    def sized(self) -> bool:
        return self.sizing != "execution" or self.sized_at is not None

    def finish(self, session: date, status: str, reason: str = "") -> None:
        self.closed, self.status, self.reason = session, status, reason

    def record(self) -> IntentRecord:
        return IntentRecord(
            self.intent_id,
            self.created,
            self.symbol,
            self.kind,
            self.quantity if self.sized else None,
            self.status,
            self.closed,
            self.reason,
            tuple(self.adjustments),
            self.weight_ppm,
            self.sizing,
            self.sized_at,
        )


class IntentBook:
    def __init__(self) -> None:
        self.history: list[Intent] = []
        self.pending: dict[str, Intent] = {}
        self.last_weights: tuple[str, tuple[int, ...]] | None = None

    def place(self, session: date, symbol: str, kind: str, quantity: int) -> int:
        if old := self.pending.pop(symbol, None):
            old.finish(session, "cancelled", "target_replaced")
        intent = Intent(len(self.history) + 1, session, symbol, kind, quantity)
        self.history.append(intent)
        self.pending[symbol] = intent
        self.last_weights = None
        return intent.intent_id

    def place_weight(
        self,
        session: date,
        symbol: str,
        weight: int,
        sizing: str,
        quantity: int,
        sized_at: date | None,
    ) -> int:
        intent_id = self.place(session, symbol, "target", quantity)
        intent = self.pending[symbol]
        intent.weight_ppm, intent.sizing, intent.sized_at = weight, sizing, sized_at
        return intent_id

    def cancel(self, session: date, intent_id: int) -> None:
        for symbol, intent in self.pending.items():
            if intent.intent_id == intent_id:
                intent.finish(session, "cancelled", "user_cancelled")
                del self.pending[symbol]
                self.last_weights = None
                return
        raise ValueError(f"no active intent {intent_id}")

    def finish(self, session: date) -> None:
        for intent in self.pending.values():
            intent.finish(session, "unexecuted", "end_of_data")
        self.pending.clear()

    def adjust(self, symbol: str, action_id: str, session: date, bonus_ppm: int) -> None:
        intent = self.pending.get(symbol)
        if intent is None or intent.kind != "target" or not bonus_ppm or not intent.sized:
            return
        previous = intent.quantity
        intent.quantity = previous * (1_000_000 + bonus_ppm) // 1_000_000
        if intent.quantity > 1_000_000_000:
            raise OverflowError("adjusted target quantity exceeds supported bounds")
        intent.adjustments.append(TargetAdjustment(action_id, session, previous, intent.quantity))
