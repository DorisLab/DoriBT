import csv
import json
from decimal import Decimal

import pytest
from engine_fixtures import data_for
from minute_fixtures import minute_data

from doribt import Backtest, BarExecution, Costs, FixedBps, FixedTicks, RunConfig, VolumeImpact

FREE = Costs(commission=0, minimum_commission=0)
POLICIES = ("strict", "cap", "cost")


def trade_at_boundary(backend, policy, change, *, buying=True, slip=None, limit=None):
    data = minute_data(days=1, frequency="5min", settlement=0, changes={1 if buying else 2: change})

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 100, limit_price=limit if buying else None)
        if not buying and ctx.bar_index == 1:
            ctx.order("A", -100, limit_price=limit)

    return Backtest(
        data,
        costs=FREE,
        execution=BarExecution(
            participation=0.1, slippage=slip or FixedTicks(2), slippage_policy=policy
        ),
    ).run(strategy, backend=backend)


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("buying", [True, False])
@pytest.mark.parametrize(
    "slip,delta", [(FixedTicks(2), 200), (FixedBps(5), 100), (VolumeImpact(0.1), 100)]
)
def test_buy_at_bar_high_and_sell_at_bar_low(backend, policy, buying, slip, delta):
    result = trade_at_boundary(
        backend, policy, {"high" if buying else "low": 10}, buying=buying, slip=slip
    )
    if policy == "strict":
        assert len(result.fills) == (0 if buying else 1)
        assert result.orders[-1].reason == "price_out_of_range"
        return
    fill = result.fills[-1]
    expected = 100000 + (delta if buying else -delta) if policy == "cost" else 100000
    assert fill.price_units == expected
    assert fill.reference_price_units == 100000
    assert fill.reference_price == 10
    assert fill.slippage_cost_units == (100 * delta if policy == "cost" else 0)
    assert fill.quantity == (100 if buying else -100)


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("buying", [True, False])
def test_crossing_daily_limit_is_distinct_from_raw_open_at_limit(backend, policy, buying):
    result = trade_at_boundary(
        backend,
        policy,
        {"upper_limit": 10.01, "lower_limit": 9.99, "high": 10.01, "low": 9.99},
        buying=buying,
    )
    if policy == "strict":
        assert result.orders[-1].reason == "price_out_of_range"
    else:
        delta = 0.01 if policy == "cap" else 0.02
        assert result.fills[-1].price == (10 + delta if buying else 10 - delta)
        assert result.orders[-1].status == "filled"

    blocked = trade_at_boundary(
        backend,
        policy,
        {"upper_limit": 10, "high": 10} if buying else {"lower_limit": 10, "low": 10},
        buying=buying,
    )
    assert len(blocked.fills) == (0 if buying else 1)
    assert blocked.orders[-1].reason == ("buy_at_upper_limit" if buying else "sell_at_lower_limit")


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("buying", [True, False])
def test_explicit_limit_protects_final_settlement_price(backend, policy, buying):
    result = trade_at_boundary(backend, policy, {}, buying=buying, limit=10)
    assert len(result.fills) == (0 if buying else 1)
    assert result.orders[-1].reason == "limit_price"


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("buying", [True, False])
def test_buying_at_lower_limit_and_selling_at_upper_limit_remain_eligible(backend, policy, buying):
    result = trade_at_boundary(
        backend,
        policy,
        {"lower_limit": 10, "low": 10} if buying else {"upper_limit": 10, "high": 10},
        buying=buying,
    )
    assert result.orders[-1].status == "filled"
    assert result.fills[-1].price == (10.02 if buying else 9.98)


@pytest.mark.parametrize("policy", ["cap", "cost"])
@pytest.mark.parametrize(
    "change,reason",
    [
        ({"status": "suspended", "volume": 0}, "suspended"),
        ({"volume": 0}, "no_volume"),
        ({"phase": "auction"}, "auction"),
    ],
)
def test_cost_policy_does_not_override_market_eligibility(backend, policy, change, reason):
    result = trade_at_boundary(backend, policy, change)
    assert not result.fills
    assert result.orders[0].reason == reason


@pytest.mark.parametrize("policy,quantity,cash", [("cap", 100, 0), ("cost", 99, 80200)])
def test_affordability_uses_final_price_without_borrowing_frozen_cash(
    backend, policy, quantity, cash
):
    # A 冻结 1000 元，B 的成交只能使用剩余 1000 元；A 在该 bar 停牌。
    data = minute_data(
        days=1,
        frequency="5min",
        changes={2: {"status": "suspended", "volume": 0}, 3: {"high": 10}},
        symbols=("A", "B"),
    )

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 100, limit_price=10, valid_for="day")
            ctx.order("B", 100)

    result = Backtest(
        data,
        initial_cash=2000,
        costs=FREE,
        execution=BarExecution(participation=1, slippage=FixedTicks(2), slippage_policy=policy),
    ).run(strategy, backend=backend)
    assert len(result.fills) == 1
    assert result.fills[0].symbol == "B"
    assert result.fills[0].quantity == quantity
    assert result.cash_units[-1] == 1000 * 10000 + cash
    assert not result.frozen_cash_units[-1]


@pytest.mark.parametrize("policy", ["cap", "cost"])
def test_partial_round_trip_ledger_and_export(backend, policy, tmp_path):
    changes = {i: {"high": 10, "low": 10} for i in range(96)}
    data = minute_data(frequency="5min", changes=changes)
    config = RunConfig(
        initial_cash=10000,
        costs=Costs(commission=0.001, minimum_commission=5),
        execution=BarExecution(slippage=FixedTicks(2), slippage_policy=policy),
        backend=backend,
    )

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 200, valid_for="day")
        elif ctx.bar_index == 47:
            ctx.order("A", -200, valid_for="day")

    result = Backtest(data, config=config).run(strategy)
    assert [f.quantity for f in result.fills] == [50] * 4 + [-50] * 4
    buy = Decimal("10.02") if policy == "cost" else Decimal(10)
    sell = Decimal("9.98") if policy == "cost" else Decimal(10)
    cash, position = Decimal(10000), 0
    for index, point in enumerate(data.timeline):
        for fill in (f for f in result.fills if f.timestamp == point):
            price = buy if fill.quantity > 0 else sell
            commission = Decimal(5) if fill.fill_id in (1, 5) else Decimal(0)
            cash -= fill.quantity * price + commission
            position += fill.quantity
            assert fill.price_units == int(price * 10000)
            assert fill.commission_units == int(commission * 10000)
        assert result.cash_units[index] == int(cash * 10000)
        assert result.holdings[index, 0] == position
        assert result.equity_units[index] == int((cash + position * 10) * 10000)
    assert result.cash[-1] == (9982 if policy == "cost" else 9990)
    assert sum(f.slippage_cost for f in result.fills) == (8 if policy == "cost" else 0)
    assert sum(f.fees for f in result.fills) == 10

    folder = tmp_path / "report"
    result.export(folder)
    ledger = json.loads((folder / "ledger.json").read_text(encoding="utf-8"))
    run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    assert run["execution"]["slippage_policy"] == policy
    assert run["config"]["slippage_policy"] == policy
    assert ledger["fills"][0]["reference_price_units"] == 100000
    with (folder / "fills.csv").open(encoding="utf-8", newline="") as stream:
        assert int(next(csv.DictReader(stream))["reference_price_units"]) == 100000


@pytest.mark.parametrize("policy,expected", [("strict", None), ("cap", 10), ("cost", 10.02)])
def test_daily_run_config_supports_same_policy_and_round_trips(backend, policy, expected):
    config = RunConfig.from_dict(
        {"slippage_value": 2, "slippage_policy": policy, "backend": backend}
    )
    rebuilt = RunConfig.from_dict(json.loads(json.dumps(config.to_dict())))
    assert rebuilt.to_dict() == config.to_dict()
    result = Backtest(data_for([10, 10]), config=config).run(
        lambda ctx: ctx.target_positions({"A": 100})
    )
    assert ([f.price for f in result.fills] or [None]) == [expected]
    assert result.run_info.to_dict()["execution"]["slippage_policy"] == policy


def test_invalid_policy_rejected_and_missing_policy_keeps_strict_default():
    with pytest.raises(ValueError, match="slippage_policy"):
        BarExecution(slippage_policy="unknown")
    with pytest.raises(ValueError, match="slippage_policy"):
        RunConfig.from_dict({"slippage_policy": "unknown"})
    assert RunConfig.from_dict({}).execution.slippage_policy == "strict"


@pytest.mark.parametrize("policy", ["strict", "cost"])
def test_nonpositive_cost_price_does_not_create_a_fill(backend, policy):
    data = minute_data(
        days=1,
        frequency="5min",
        settlement=0,
        changes={1: {"high": 20, "upper_limit": None, "lower_limit": None}},
    )

    def strategy(ctx):
        if ctx.bar_index == 0:
            ctx.order("A", 100)
        if ctx.bar_index == 1:
            ctx.order("A", -100)

    result = Backtest(
        data,
        costs=FREE,
        execution=BarExecution(participation=1, slippage=FixedBps(10000), slippage_policy=policy),
    ).run(strategy, backend=backend)
    assert [f.quantity for f in result.fills] == [100]
    assert result.orders[-1].reason == "price_out_of_range"
