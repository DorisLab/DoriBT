"""Independent Decimal accounting; deliberately linear search, not engine formulas."""

from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pytest
from engine_fixtures import data_for
from hypothesis import given, settings
from hypothesis import strategies as st

from doribt import Backtest, Costs


def decimal_reference(prices, intents, commission, minimum, settlement):
    cash = Decimal("5000")
    lots = [[], []]
    cash_curve, positions = [50_000_000], [[0, 0]]
    for index in range(1, 5):
        requested = intents[index - 1]
        sequence = sorted(range(2), key=lambda column: (requested[column] > 0, column))
        for column in sequence:
            price = Decimal(prices[column][index]) / 100
            requested_quantity = requested[column]
            quantity = abs(requested_quantity)
            sign = 1 if requested_quantity > 0 else -1
            if sign < 0:
                available = sum(lot[0] for lot in lots[column] if lot[1] <= index)
                quantity = min(quantity, available)
            while quantity:
                value = price * quantity
                fee = max(minimum, (value * commission).quantize(Decimal(".01"), ROUND_HALF_UP))
                stamp = value * Decimal(".0005") if sign < 0 else Decimal(0)
                stamp = stamp.quantize(Decimal(".01"), ROUND_HALF_UP)
                transfer = (value * Decimal(".00001")).quantize(Decimal(".01"), ROUND_HALF_UP)
                change = -sign * value - fee - stamp - transfer
                if cash + change >= 0:
                    cash += change
                    break
                quantity -= 100
            if sign > 0 and quantity:
                lots[column].append([quantity, index + settlement])
            elif sign < 0:
                remaining = quantity
                for lot in lots[column]:
                    if lot[1] <= index:
                        part = min(remaining, lot[0])
                        lot[0] -= part
                        remaining -= part
            lots[column] = [lot for lot in lots[column] if lot[0]]
        cash_curve.append(int(cash * 10_000))
        positions.append([sum(lot[0] for lot in security) for security in lots])
    return cash_curve, positions


@pytest.mark.parametrize("backend", ["python", pytest.param("numba", marks=pytest.mark.numba)])
@settings(max_examples=60, deadline=None, derandomize=True)
@given(
    a=st.lists(st.integers(200, 2500), min_size=5, max_size=5),
    b=st.lists(st.integers(200, 2500), min_size=5, max_size=5),
    intents=st.lists(
        st.tuples(st.sampled_from([-300, -100, 100, 300]), st.sampled_from([-300, -100, 100, 300])),
        min_size=4,
        max_size=4,
    ),
    commission=st.sampled_from(["0", ".0003", ".003", ".01"]),
    minimum=st.sampled_from(["0", "1", "5"]),
    settlement=st.integers(0, 2),
)
def test_shared_cash_and_settlement_against_decimal(
    backend, a, b, intents, commission, minimum, settlement
):
    data = data_for(
        [str(Decimal(value) / 100) for value in a],
        [str(Decimal(value) / 100) for value in b],
        settlement=settlement,
        rule_changes={"stamp_duty_sell": ".0005", "transfer_fee": ".00001"},
    )

    def strategy(ctx):
        index = data.sessions.index(ctx.session)
        if index < 4:
            for column, symbol in enumerate(ctx.symbols):
                ctx.order(symbol, intents[index][column])

    result = Backtest(
        data, initial_cash=5000, costs=Costs(commission=commission, minimum_commission=minimum)
    ).run(strategy, backend=backend)
    cash, positions = decimal_reference(
        [a, b], intents, Decimal(commission), Decimal(minimum), settlement
    )
    np.testing.assert_array_equal(result.cash_units, cash)
    np.testing.assert_array_equal(result.holdings, positions)
    prices = np.array([a, b], dtype=np.int64).T * 100
    np.testing.assert_array_equal(
        result.equity_units, np.array(cash) + np.sum(prices * positions, axis=1)
    )
    assert np.all(result.cash_units >= 0)
    assert np.all(result.sellable <= result.holdings)
