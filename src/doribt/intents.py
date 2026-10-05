"""Pending targets are distinct from their one-session child orders."""

from dataclasses import dataclass
from datetime import date

from .orders import IntentRecord


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

    def finish(self, session: date, status: str, reason: str = "") -> None:
        self.closed, self.status, self.reason = session, status, reason

    def record(self) -> IntentRecord:
        return IntentRecord(
            self.intent_id,
            self.created,
            self.symbol,
            self.kind,
            self.quantity,
            self.status,
            self.closed,
            self.reason,
        )


class IntentBook:
    def __init__(self) -> None:
        self.history: list[Intent] = []
        self.pending: dict[str, Intent] = {}
        self.last_weights: tuple[int, ...] | None = None

    def place(self, session: date, symbol: str, kind: str, quantity: int) -> int:
        if old := self.pending.pop(symbol, None):
            old.finish(session, "cancelled", "target_replaced")
        intent = Intent(len(self.history) + 1, session, symbol, kind, quantity)
        self.history.append(intent)
        self.pending[symbol] = intent
        self.last_weights = None
        return intent.intent_id

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
