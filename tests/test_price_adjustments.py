"""Price research must not borrow future factors or change the account price basis."""

from dataclasses import replace
from decimal import Decimal

import numpy as np
import pytest
from corporate_fixtures import distribution, market_with_actions

from doribt import Backtest, Costs, PriceAdjustment, WeightTargets


def adjustment(**changes):
    return PriceAdjustment(
        **(
            dict(
                action_id="d1",
                factor="0.9",
                known_on="2025-01-03",
                source="fictional reference ratio",
            )
            | changes
        )
    )


def data_with_factors():
    raw = market_with_actions([10, 10, 9, 9, 9], [distribution()], b=[20] * 5)
    return replace(raw, adjustments=(adjustment(),))


def test_raw_and_asof_prices_have_distinct_explicit_time_semantics():
    data = data_with_factors()
    before = data.prices("close", adjustment="asof", as_of="2025-01-03")
    np.testing.assert_allclose(before, [[10, 20], [10, 20]])
    after = data.prices("close", adjustment="asof", as_of="2025-01-06")
    np.testing.assert_allclose(after, [[9, 20], [9, 20], [9, 20]])
    np.testing.assert_allclose(data.prices("close")[:, 0], [10, 10, 9, 9, 9])
    assert data.prices("close", as_of="2025-01-03").shape == (2, 2)
    assert not after.flags.writeable
    with pytest.raises(ValueError, match="explicit as_of"):
        data.prices("close", adjustment="asof")
    with pytest.raises(ValueError, match="supplied trading session"):
        data.prices("close", as_of="2025-01-04")
    with pytest.raises(ValueError, match="adjustment must"):
        data.prices("close", adjustment="latest")


def test_callback_history_defaults_raw_and_window_never_changes_account(backend):
    data = data_with_factors()
    seen = []

    def strategy(ctx):
        raw = ctx.history("A")
        adjusted = ctx.history("A", adjustment="asof")
        window = ctx.history("A", adjustment="asof", bars=2, field="open")
        seen.append((raw.tolist(), adjusted.tolist(), window.tolist()))
        assert not adjusted.flags.writeable
        np.testing.assert_allclose(adjusted[-len(window) :], window)
        ctx.target_positions({"A": 100})

    engine = Backtest(data, initial_cash=10000, costs=Costs(commission=0, minimum_commission=0))
    researched = engine.run(strategy, backend=backend)
    baseline = engine.run(lambda ctx: ctx.target_positions({"A": 100}), backend=backend)
    assert seen[1] == ([10, 10], [10, 10], [10, 10])
    assert seen[2] == ([10, 10, 9], [9, 9, 9], [9, 9])
    assert seen[-1][0] == [10, 10, 9, 9, 9]
    assert researched.orders == baseline.orders
    np.testing.assert_array_equal(researched.equity_units, baseline.equity_units)
    assert researched.fills[0].price == 10
    assert researched.entitlements[0].cash_units == 1000000
    assert researched.equity[-1] == 10000
    assert researched.run_info.to_dict()["data"]["adjustments"][0]["factor"] == "0.9"


def test_future_events_and_changed_future_prices_cannot_change_prior_decisions(backend):
    first = data_with_factors()
    later = distribution(
        action_id="d2",
        record_date="2025-01-07",
        ex_date="2025-01-08",
        pay_date="2025-01-08",
        cash_per_share=2,
    )
    inputs = replace(
        first,
        actions=(*first.actions, later),
        adjustments=(
            *first.adjustments,
            adjustment(action_id="d2", factor="0.75", known_on="2025-01-07"),
        ),
    )
    alternate = replace(
        inputs,
        adjustments=(adjustment(), adjustment(action_id="d2", factor=".5", known_on="2025-01-07")),
    )
    changed_bars = tuple(
        replace(bar, open=50000, high=50000, low=50000, close=50000)
        if bar.symbol == "A" and str(bar.session) == "2025-01-08"
        else bar
        for bar in alternate.bars
    )
    alternate = replace(alternate, bars=changed_bars)
    histories = []
    for data in (inputs, alternate):
        seen = []

        def callback(ctx, seen=seen):
            values = ctx.history("A", adjustment="asof")
            seen.append(values.tolist())

        Backtest(data).run(callback, backend=backend)
        histories.append(seen)
    assert histories[0][:-1] == histories[1][:-1]
    assert histories[0][-1] == [6.75] * 4 + [9]
    assert histories[1][-1] == [4.5] * 4 + [5]


def test_missing_or_late_factor_fails_only_when_requested_history_crosses_event():
    data = data_with_factors()
    late = replace(data, adjustments=(adjustment(known_on="2025-01-08"),))
    missing = replace(data, adjustments=())
    for value in (late, missing):
        value.prices("close", adjustment="asof", as_of="2025-01-03")
        with pytest.raises(ValueError, match="unavailable as of 2025-01-06: d1"):
            value.prices("close", adjustment="asof", as_of="2025-01-06")

        # One current bar doesn't cross an ex-date. Other symbols need no unrelated factor.
        def callback(ctx):
            ctx.history("A", bars=1, adjustment="asof")
            ctx.history("B", adjustment="asof")

        Backtest(value).run(callback)
    assert late.prices("close", adjustment="asof", as_of="2025-01-08")[0, 0] == 9


def test_factor_is_not_guessed_from_account_cash_and_cannot_double_count_it():
    raw = market_with_actions([10, 10, 8], [distribution()])
    data = replace(raw, adjustments=(adjustment(factor="0.8"),))
    result = Backtest(
        data, initial_cash=10000, costs=Costs(commission=0, minimum_commission=0)
    ).run(WeightTargets(sessions=data.sessions, weights={"A": [0.1, 0.1, 0.1]}))
    assert data.prices("close", adjustment="asof", as_of="2025-01-06")[:, 0].tolist() == [8, 8, 8]
    assert result.equity[-1] == 9900
    assert result.dividend_receivable[-1] == 100
    assert result.fills[0].price == 10


def test_same_date_actions_require_consolidation_instead_of_compounding_targets():
    original = distribution()
    duplicate = replace(original, action_id="different-id")
    with pytest.raises(ValueError, match="consolidated event"):
        market_with_actions([10] * 3, [original, duplicate])


@pytest.mark.parametrize("factor", [0, -1, True, "bad", "NaN", "Infinity", "1e-101", "1e101"])
def test_invalid_adjustment_factors_rejected(factor):
    with pytest.raises(ValueError, match="factor"):
        adjustment(factor=factor)


def test_factor_identity_dates_and_fingerprint_are_checked():
    data = data_with_factors()
    assert replace(data, adjustments=()).fingerprint != data.fingerprint
    assert (
        replace(data, adjustments=(adjustment(source="another source"),)).fingerprint
        != data.fingerprint
    )
    with pytest.raises(ValueError, match="duplicate price adjustment"):
        replace(data, adjustments=(adjustment(), adjustment()))
    with pytest.raises(ValueError, match="unknown action"):
        replace(data, adjustments=(adjustment(action_id="absent"),))
    with pytest.raises(ValueError, match="before announcement"):
        replace(data, adjustments=(adjustment(known_on="2024-12-31"),))
    with pytest.raises(ValueError, match="source"):
        adjustment(source=" ")


def test_adjusted_factors_are_float_research_values_not_limited_to_price_ticks():
    data = replace(data_with_factors(), adjustments=(adjustment(factor=Decimal(1) / 3),))
    prices = data.prices("close", adjustment="asof", as_of="2025-01-06")
    assert prices[0, 0] == pytest.approx(10 / 3)
    assert data.prices("close")[0, 0] == 10
