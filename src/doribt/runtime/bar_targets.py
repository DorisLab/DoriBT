"""Persistent position intents issue daily child orders through the same broker."""

from datetime import date

from doribt.kernels.execution import BUY_STEP, MINIMUM, OPEN, ORDER_MAXIMUM, SELL_STEP, TICK
from doribt.runtime.broker import Broker
from doribt.runtime.intents import IntentBook
from doribt.runtime.sizing import weight_quantity


class BarIntentBook(IntentBook):
    def __init__(self, broker: Broker) -> None:
        super().__init__()
        self.broker = broker
        self.children: dict[int, int] = {}

    def _cancel_child(self, intent_id: int) -> None:
        order_id = self.children.pop(intent_id, 0)
        if order_id in self.broker.active:
            self.broker.cancel(order_id)

    def place(self, session: date, symbol: str, kind: str, quantity: int) -> int:
        if old := self.pending.get(symbol):
            self._cancel_child(old.intent_id)
        return super().place(session, symbol, kind, quantity)

    def cancel(self, session: date, intent_id: int) -> None:
        super().cancel(session, intent_id)
        self._cancel_child(intent_id)

    def resolve_weights(self, index: int, pending_shares: dict[str, int], equity: int) -> None:
        """同一开盘、成交前统一定量；后续部分成交沿用已确定的股数。"""
        broker, data = self.broker, self.broker.data
        positions = broker.account.quantities()
        session = data.sessions[data.day_index(index)]
        for symbol, intent in self.pending.items():
            if intent.sized:
                continue
            column = data.symbols.index(symbol)
            weight = intent.weight_ppm
            assert weight is not None
            intent.quantity = (
                0
                if not weight
                else weight_quantity(
                    equity,
                    weight,
                    int(broker.compiled.market[index, column, OPEN]),
                    int(positions[column]) + pending_shares[symbol],
                    data.rules.at(symbol, session).rule,
                )
            )
            intent.sized_at = data.timeline[index]

    def sync(self, index: int, pending_shares: dict[str, int]) -> None:
        broker, data = self.broker, self.broker.data
        broker.index = index - 1
        positions = broker.account.quantities()
        for symbol, intent in tuple(self.pending.items()):
            column = data.symbols.index(symbol)
            difference = intent.quantity - int(positions[column]) - pending_shares[symbol]
            if not difference:
                self._cancel_child(intent.intent_id)
                intent.finish(data.sessions[data.day_index(index)], "fulfilled")
                del self.pending[symbol]
            elif self.children.get(intent.intent_id) not in broker.active:
                self._issue(index, column, intent.intent_id, difference)
        broker.index = index

    def _issue(self, index: int, column: int, intent_id: int, difference: int) -> None:
        broker = self.broker
        previous = self.children.get(intent_id)
        # A rejected/day-expired child is retried on the next trading day, not every minute.
        if previous is not None:
            order = broker.orders[previous - 1]
            if (
                order.status != "filled"
                and order.session == broker.data.sessions[broker.data.day_index(index)]
            ):
                return
        execution_sizing = self.pending[broker.data.symbols[column]].sizing == "execution"
        rule = broker.compiled.market[index if execution_sizing else index - 1, column]
        if not rule[TICK]:
            return  # 未上市／退市没有有效申报规则，保留意图，不生成子单。
        maximum = int(rule[ORDER_MAXIMUM])
        if maximum and abs(difference) > maximum:
            if difference < 0:
                difference = -(maximum // int(rule[SELL_STEP]) * int(rule[SELL_STEP]))
            else:
                minimum, step = int(rule[MINIMUM]), int(rule[BUY_STEP])
                difference = minimum + (maximum - minimum) // step * step
        if difference > 0:
            minimum, step = int(rule[MINIMUM]), int(rule[BUY_STEP])
            if difference < minimum:
                self.pending[broker.data.symbols[column]].reason = "target_below_minimum"
                return
            difference = minimum + (difference - minimum) // step * step
        self.children[intent_id] = broker.submit(
            broker.data.symbols[column],
            difference,
            "day",
            intent_id=intent_id,
            sizing_index=index if execution_sizing else None,
        )
