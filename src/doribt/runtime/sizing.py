"""权重定量：价格时点由调用者明确选择，数量约束保持一致。"""

from doribt.market.rules import TradingRule


def validate_sizing(sizing: str) -> None:
    if sizing not in {"close", "execution"}:
        raise ValueError("sizing must be close or execution")


def weight_quantity(equity: int, weight: int, price: int, current: int, rule: TradingRule) -> int:
    if not weight:
        return 0
    if price <= 0:
        raise ValueError("cannot size a target without a current valuation")
    desired = equity * weight // 1_000_000 // price
    if desired > 1_000_000_000:
        raise OverflowError("target quantity exceeds supported bounds")
    if desired > current:
        extra = desired - current
        extra = (
            0
            if extra < rule.buy_minimum
            else rule.buy_minimum + (extra - rule.buy_minimum) // rule.buy_step * rule.buy_step
        )
        return current + extra
    reduction = (current - desired) // rule.sell_step * rule.sell_step
    return current - (0 if reduction < rule.sell_minimum else reduction)
