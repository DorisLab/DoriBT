"""Independent Decimal account for the validation harness's narrow ETF model.

No DoriBT execution, fee, sizing or accounting helpers are imported here. Inputs
are prescribed close weights, original CSV strings and explicit cost assumptions.
This oracle supports one ordinary T+1 ETF, 100-share lots, and no distributions.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class Reference:
    cash: tuple[Decimal, ...]
    equity: tuple[Decimal, ...]
    holdings: tuple[int, ...]
    fills: tuple[tuple[str, int, Decimal, Decimal], ...]
    blocked: tuple[tuple[str, str], ...]


def fee(quantity: int, price: Decimal, rate: Decimal, minimum: Decimal) -> Decimal:
    return max(abs(quantity) * price * rate, minimum).quantize(
        Decimal(".01"), rounding=ROUND_HALF_UP
    )


def blocked(row: Mapping[str, str], quantity: int, price: Decimal) -> str | None:
    opening = Decimal(row["open"])
    if row["status"] == "suspended":
        return "suspended"
    if Decimal(row["volume"]) == 0:
        return "no_volume"
    if row["upper_limit"] and quantity > 0 and opening >= Decimal(row["upper_limit"]):
        return "buy_at_upper_limit"
    if row["lower_limit"] and quantity < 0 and opening <= Decimal(row["lower_limit"]):
        return "sell_at_lower_limit"
    if row["upper_limit"] and price > Decimal(row["upper_limit"]):
        return "price_out_of_range"
    if row["lower_limit"] and price < Decimal(row["lower_limit"]):
        return "price_out_of_range"
    return None


def affordable(
    quantity: int, price: Decimal, cash: Decimal, rate: Decimal, minimum: Decimal
) -> int:
    count = quantity
    while count > 0 and count * price + fee(count, price, rate, minimum) > cash:
        count -= 100
    return count


def reference(
    rows: Sequence[Mapping[str, str]],
    weights: Sequence[float],
    *,
    initial_cash: str = "100000",
    rate: str = ".0003",
    minimum: str = "5",
    slippage: str = ".001",
) -> Reference:
    if len(rows) != len(weights):
        raise ValueError("weights and rows must align")
    if any(row["status"] not in {"trading", "suspended"} for row in rows):
        raise ValueError("oracle supports only listed ordinary ETF sessions")
    cash, commission, min_fee, slip = map(Decimal, (initial_cash, rate, minimum, slippage))
    quantity, target = 0, 0
    last_weight: Decimal | None = None
    cash_history, equity_history, positions, fills, failures = [], [], [], [], []
    for row, raw_weight in zip(rows, weights, strict=True):
        requested = max(-1_000_000, min(target - quantity, 1_000_000))
        if requested:
            price = Decimal(row["open"]) + (slip if requested > 0 else -slip)
            reason = blocked(row, requested, price)
            if reason is not None:
                failures.append((row["session"], reason))
            else:
                executed = (
                    requested
                    if requested < 0
                    else affordable(requested, price, cash, commission, min_fee)
                )
                if executed:
                    charge = fee(executed, price, commission, min_fee)
                    cash -= executed * price + charge
                    quantity += executed
                    fills.append((row["session"], executed, price, charge))
                if executed != requested:
                    failures.append((row["session"], "insufficient_cash"))
        equity = cash + quantity * Decimal(row["close"])
        cash_history.append(cash)
        equity_history.append(equity)
        positions.append(quantity)
        weight = Decimal(str(raw_weight))
        if weight != last_weight:
            target = int(equity * weight / Decimal(row["close"]) / 100) * 100
            last_weight = weight
    return Reference(
        tuple(cash_history), tuple(equity_history), tuple(positions), tuple(fills), tuple(failures)
    )
