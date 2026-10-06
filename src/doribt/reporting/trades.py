"""Moving-average price PnL; distributions and dividend tax remain separate."""

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from fractions import Fraction
from typing import TYPE_CHECKING, Any

from doribt.accounting.orders import Fill

if TYPE_CHECKING:
    from doribt.reporting.result import BacktestResult


@dataclass(frozen=True)
class Sale:
    fill_id: int
    order_id: int
    symbol: str
    timestamp: date
    quantity: int
    proceeds: float
    cost: float
    fees: float
    price_pnl: float


@dataclass(frozen=True)
class RoundTrip:
    symbol: str
    opened: date
    closed: date
    holding_days: int
    price_pnl: float


@dataclass(frozen=True)
class OpenPosition:
    symbol: str
    opened: date
    quantity: int
    cost: float
    market_value: float
    realized_price_pnl: float
    unrealized_price_pnl: float


@dataclass
class _Position:
    quantity: int = 0
    cost: Fraction = field(default_factory=Fraction)
    realized: Fraction = field(default_factory=Fraction)
    opened: date | None = None

    def add(self, quantity: int, cost: int, session: date) -> None:
        if not self.quantity:
            self.opened, self.realized = session, Fraction()
        self.quantity += quantity
        self.cost += cost

    def sell(self, fill: Fill) -> Sale:
        quantity = -fill.quantity
        if quantity > self.quantity:
            raise ValueError("sale exceeds economic position during PnL reconstruction")
        basis = self.cost * quantity / self.quantity
        fees = fill.commission_units + fill.stamp_duty_units + fill.transfer_fee_units
        proceeds = quantity * fill.price_units
        pnl = proceeds - fees - basis
        self.quantity -= quantity
        self.cost -= basis
        self.realized += pnl
        return Sale(
            fill.fill_id,
            fill.order_id,
            fill.symbol,
            fill.timestamp or fill.session,
            quantity,
            proceeds / 10_000,
            float(basis / 10_000),
            fees / 10_000,
            float(pnl / 10_000),
        )


@dataclass(frozen=True)
class TradeAnalysis:
    sales: tuple[Sale, ...]
    closed: tuple[RoundTrip, ...]
    positions: tuple[OpenPosition, ...]
    dividend_income: float
    dividend_tax: float

    def stats(self) -> dict[str, float | int | None]:
        profits = [item.price_pnl for item in self.closed if item.price_pnl > 0]
        losses = [-item.price_pnl for item in self.closed if item.price_pnl < 0]
        realized = sum(sale.price_pnl for sale in self.sales)
        unrealized = sum(position.unrealized_price_pnl for position in self.positions)
        return {
            "closed_trade_count": len(self.closed),
            "open_trade_count": len(self.positions),
            "win_rate": len(profits) / len(self.closed) if self.closed else None,
            "profit_factor": sum(profits) / sum(losses) if losses else None,
            "payoff_ratio": (sum(profits) / len(profits)) / (sum(losses) / len(losses))
            if profits and losses
            else None,
            "average_holding_days": sum(item.holding_days for item in self.closed)
            / len(self.closed)
            if self.closed
            else None,
            "realized_price_pnl": realized,
            "unrealized_price_pnl": unrealized,
            "dividend_income": self.dividend_income,
            "total_pnl": realized + unrealized + self.dividend_income - self.dividend_tax,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _open_positions(
    result: "BacktestResult", positions: dict[str, _Position]
) -> tuple[OpenPosition, ...]:
    opened = []
    for j, symbol in enumerate(result.symbols):
        position = positions[symbol]
        quantity = int(result.holdings[-1, j]) + int(result.pending_shares[-1, j])
        if position.quantity != quantity:
            raise ValueError("reconstructed economic position differs from account")
        if quantity:
            assert position.opened is not None
            value = quantity * int(result.close_units[-1, j])
            opened.append(
                OpenPosition(
                    symbol,
                    position.opened,
                    quantity,
                    float(position.cost / 10_000),
                    value / 10_000,
                    float(position.realized / 10_000),
                    float((value - position.cost) / 10_000),
                )
            )
    return tuple(opened)


def analyze_trades(result: "BacktestResult") -> TradeAnalysis:
    positions = {symbol: _Position() for symbol in result.symbols}
    by_day: dict[date, list[Fill]] = defaultdict(list)
    for fill in result.fills:
        by_day[fill.session].append(fill)
    bonuses: dict[date, list[tuple[str, int]]] = defaultdict(list)
    for event in result.corporate_events:
        if event.kind == "accrued" and event.quantity:
            bonuses[event.session].append((event.symbol, event.quantity))
    sales, closed = [], []
    for session in sorted(by_day.keys() | bonuses.keys()):
        for symbol, quantity in bonuses[session]:
            positions[symbol].add(quantity, 0, session)
        for fill in by_day[session]:
            position = positions[fill.symbol]
            if fill.quantity > 0:
                cost = fill.quantity * fill.price_units
                cost += fill.commission_units + fill.stamp_duty_units + fill.transfer_fee_units
                position.add(fill.quantity, cost, session)
            else:
                sales.append(position.sell(fill))
                if not position.quantity:
                    assert position.opened is not None
                    closed.append(
                        RoundTrip(
                            fill.symbol,
                            position.opened,
                            session,
                            (session - position.opened).days,
                            float(position.realized / 10_000),
                        )
                    )
    dividends = sum(e.amount_units for e in result.corporate_events if e.kind == "accrued")
    taxes = sum(tax.amount_units for tax in result.taxes)
    return TradeAnalysis(
        tuple(sales),
        tuple(closed),
        _open_positions(result, positions),
        dividends / 10_000,
        taxes / 10_000,
    )
