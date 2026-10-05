import pytest
from engine_fixtures import data_for

from doribt import Backtest, Costs, Reason

FREE = Costs(commission=0, minimum_commission=0)
STAR = dict(buy_minimum=200, buy_step=1, sell_minimum=200, sell_step=1, order_maximum=100_000)


def test_small_star_sale_is_not_legal_merely_because_step_is_one(backend):
    data = data_for([10] * 4, rule_changes=STAR)

    def strategy(ctx):
        index = len(ctx.history("A"))
        if index == 1:
            ctx.order("A", 201)
        elif index == 2:
            ctx.order("A", -1)
        elif index == 3:
            ctx.target_positions({"A": 0})

    result = Backtest(data, costs=FREE).run(strategy, backend=backend)
    assert result.orders[1].reason == Reason.INVALID_QUANTITY
    assert [f.quantity for f in result.fills] == [201, -201]


def test_weight_sizing_does_not_emit_under_minimum_star_reduction(backend):
    data = data_for([10] * 4, rule_changes=STAR)

    def strategy(ctx):
        if ctx.session == data.sessions[0]:
            ctx.target_positions({"A": 201})
        elif ctx.session == data.sessions[1]:
            ctx.target_weights({"A": ".5"})
        else:
            ctx.target_weights({"A": 0})

    result = Backtest(data, initial_cash=2010, costs=FREE).run(strategy, backend=backend)
    assert [f.quantity for f in result.fills] == [201, -201]
    assert result.holdings[:, 0].tolist() == [0, 201, 201, 0]


def test_targets_remain_active_across_capped_daily_child_orders(backend):
    data = data_for([10] * 5, rule_changes=STAR)

    def strategy(ctx):
        if ctx.session == data.sessions[0]:
            ctx.target_positions({"A": 200201})

    result = Backtest(data, initial_cash=3_000_000, costs=FREE).run(strategy, backend=backend)
    assert [f.quantity for f in result.fills] == [100000, 100000, 201]
    assert [o.quantity for o in result.orders] == [100000, 100000, 201]
    assert result.intents[0].closed == data.sessions[3]
    assert result.intents[0].status == "fulfilled"
    assert result.holdings[-1, 0] == 200201


def test_oversize_single_order_is_rejected_not_silently_split(backend):
    data = data_for([10] * 3, rule_changes=STAR)

    def strategy(ctx):
        if ctx.session == data.sessions[0]:
            ctx.order("A", 100001)

    result = Backtest(data, initial_cash=3_000_000, costs=FREE).run(strategy, backend=backend)
    assert result.orders[0].reason == Reason.INVALID_QUANTITY
    assert result.intents[0].status == "rejected"
    assert not result.fills


def test_capped_target_can_sell_a_final_odd_balance(backend):
    data = data_for([10] * 5, rule_changes=STAR)

    def strategy(ctx):
        if ctx.session == data.sessions[0]:
            ctx.target_positions({"A": 100001})
        elif ctx.session == data.sessions[2]:
            ctx.target_positions({"A": 0})

    # Leave 200 for the second buy, rather than stranding an unbuyable 1-share tail.
    # On exit the final 1 share is a legal full liquidation of the remaining balance.
    result = Backtest(data, initial_cash=3_000_000, costs=FREE).run(strategy, backend=backend)
    assert [f.quantity for f in result.fills] == [99801, 200, -100000, -1]
    assert result.intents[0].status == "fulfilled"
    assert result.intents[1].status == "fulfilled"


@pytest.mark.parametrize(
    "change", [{"sell_minimum": 0}, {"order_maximum": 100}, {"instrument_kind": "bond"}]
)
def test_invalid_quantity_policy_fails_before_execution(change):
    with pytest.raises(ValueError):
        data_for([10], rule_changes=STAR | change)
