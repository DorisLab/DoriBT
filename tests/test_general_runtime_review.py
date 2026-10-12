"""共享执行与回调快照的独立对抗性复核。

在基线和候选版本的独立进程直接运行，输出全部结果字段指纹；
pytest 同时验证独立定义的快照不变量。
"""

import argparse
import hashlib
import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date

import numpy as np
import pytest
from broker_review_fixtures import broker_growth_case
from corporate_fixtures import distribution, market_with_actions
from minute_fixtures import minute_data
from minute_review_fixtures import minute_random_case
from test_weight_schedule_review import WEIGHT_CASES, inactive_weight_case

from doribt import Backtest, BarExecution, Costs, PositionTargets
from doribt.accounting.account import Position

FREE = Costs(commission=0, minimum_commission=0)


def canonical(value):
    if isinstance(value, np.ndarray):
        return dict(
            dtype=str(value.dtype),
            shape=value.shape,
            values=value.tolist(),
            writeable=value.flags.writeable,
        )
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [canonical(item) for item in value]
    return value


def digest(value):
    return hashlib.sha256(
        json.dumps(canonical(value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def distribution_pair():
    return (
        distribution(
            action_id="first",
            record_date="2025-01-02",
            ex_date="2025-01-03",
            pay_date="2025-01-04",
            bonus_per_share=1,
            share_credit_date="2025-01-03",
            share_listing_date="2025-01-06",
            taxable_bonus_amount_per_share=0,
        ),
        distribution(
            action_id="second",
            record_date="2025-01-03",
            ex_date="2025-01-06",
            pay_date="2025-01-06",
            cash_per_share=".37",
        ),
    )


def minute_snapshot_case(backend, *, frequency="5min", settlement=0):
    """延后首次访问，识别惰性映射是否误用实时账户状态。"""
    data = minute_data(
        days=3,
        frequency=frequency,
        symbols=("A", "B"),
        settlement=settlement,
        volume=1000,
        actions=distribution_pair(),
    )
    saved, observed, submitted = [], [], []
    per_day = len(data.timeline) // 3

    def strategy(ctx, *, quantity):
        saved.append(ctx)
        # 此处不读取持仓；首次访问必须在全部成交结束之后。
        if ctx.bar_index == 0:
            submitted.append(ctx.order("A", quantity, valid_for="day"))
        if ctx.bar_index == 2:
            submitted.append(ctx.order("B", 200, valid_for="day", limit_price=9))
        if ctx.bar_index == 4:
            ctx.cancel_order(submitted[-1])
        if ctx.bar_index == per_day:
            ctx.order("A", -1000, valid_for="day")
        if ctx.bar_index == 2 * per_day:
            ctx.target_positions({"B": 200, "A": 0})
        observed.append(
            (
                ctx.now,
                ctx.session,
                ctx.orders,
                ctx.intents,
                ctx.history("A", bars=2),
                ctx.account.cash,
                ctx.account.frozen_cash,
                ctx.account.available_cash,
            )
        )
        ctx.record(index=ctx.bar_index, cash=ctx.account.cash)

    test = Backtest(data, costs=FREE, execution=BarExecution(participation=".1"))
    result = test.run(strategy, parameters={"quantity": 1000}, backend=backend)
    # 刻意先完成另一次回测，再读取旧账户视图。
    test.run(
        lambda ctx: ctx.target_positions({"B": 300}) if ctx.bar_index == 0 else None,
        backend=backend,
    )
    snapshots = []
    for ctx in reversed(saved):
        index = ctx.bar_index
        expected = {
            symbol: Position(
                symbol,
                int(result.holdings[index, col]),
                int(result.sellable[index, col]),
                int(result.holdings[index, col] + result.pending_shares[index, col])
                * int(result.close_units[index, col])
                / 10000,
                int(result.pending_shares[index, col]),
                int(result.reserved_shares[index, col]),
            )
            for col, symbol in enumerate(result.symbols)
        }
        positions = ctx.account.positions
        assert isinstance(positions, Mapping)
        assert len(positions) == 2
        assert tuple(positions) == result.symbols
        assert positions == expected and expected == positions
        assert positions.copy() == expected
        assert positions | {"extra": expected["A"]} == expected | {"extra": expected["A"]}
        assert {"extra": expected["B"]} | positions == {"extra": expected["B"]} | expected
        assert tuple(reversed(positions)) == tuple(reversed(expected))
        assert repr(positions) == f"mappingproxy({expected!r})"
        assert list(positions.items()) == list(expected.items())
        assert list(positions.values()) == list(expected.values())
        assert positions.get("unknown") is None
        with pytest.raises(KeyError):
            positions["unknown"]
        with pytest.raises(TypeError):
            positions["A"] = expected["A"]
        assert ctx.account.cash == result.cash[index]
        assert ctx.account.equity == result.equity[index]
        assert ctx.account.dividend_receivable == result.dividend_receivable[index]
        assert ctx.account.tax_payable == result.tax_payable[index]
        assert ctx.account.frozen_cash == result.reserved_cash_units[index] / 10000
        for position in positions.values():
            assert position.available_quantity == max(
                0, position.sellable - position.frozen_quantity
            )
        try:
            adjusted = ctx.history("A", bars=2, adjustment="asof")
        except ValueError as error:
            adjusted = (type(error).__name__, str(error))
        snapshots.append((index, ctx.account, ctx.history("A", bars=2), adjusted))
        with pytest.raises(RuntimeError, match="active strategy callback"):
            ctx.record(late=1)
        with pytest.raises(RuntimeError, match="close callback"):
            ctx.order("A", 100)
    return result, (snapshots, observed)


def daily_corporate_case(backend, *, scheduled):
    """重叠权益、延后股份到账，以及分红到账前卖出。"""
    actions = (
        distribution(
            action_id="first",
            cash_per_share=".371",
            bonus_per_share=1,
            share_credit_date="2025-01-07",
            share_listing_date="2025-01-09",
            taxable_bonus_amount_per_share=".13",
        ),
        distribution(
            action_id="second",
            record_date="2025-01-06",
            ex_date="2025-01-07",
            pay_date="2025-01-09",
            cash_per_share=".013",
        ),
    )
    data = market_with_actions([10, 11, 5, 6, 7, 8], actions, b=[20, 19, 18, 17, 16, 15])
    target = PositionTargets(
        sessions=data.timeline,
        quantities={"B": [100, 200, 100, 0, 100, 0], "A": [300, 300, 0, 0, 0, 0]},
    )
    test = Backtest(
        data,
        costs=Costs(commission=".0003", minimum_commission=5),
        execution=BarExecution(participation=".1"),
    )
    result = test.run(target if scheduled else lambda ctx: target(ctx), backend=backend)
    assert len(result.entitlements) == 2
    assert result.pending_shares[2, 0] == 300
    assert result.holdings[3, 0] >= 300
    assert result.sellable[3, 0] == 0
    return result, ()


def minute_persistent_target_case(backend, *, scheduled):
    """目标跨停牌间隔、子委托拒绝及日末到期后仍然有效。"""
    changes = {index: {"status": "suspended", "volume": 0} for index in range(44, 53)}
    data = minute_data(days=3, frequency="5min", volume=1000, settlement=1, changes=changes)
    quantities = [0] * 43 + [1000] * 53 + [0] * 48
    target = PositionTargets(sessions=data.timeline, quantities={"A": quantities})
    result = Backtest(data, costs=FREE, execution=BarExecution(participation=".1")).run(
        target if scheduled else lambda ctx: target(ctx), backend=backend
    )
    assert any(order.status == "expired" for order in result.orders)
    assert result.holdings[-1, 0] == 0
    return result, ()


def legacy_snapshot_case(backend):
    data = market_with_actions([10, 11, 5, 6, 7, 8], [distribution()], b=[20] * 6)
    saved = []

    def strategy(ctx):
        saved.append(ctx)
        if ctx.bar_index == 0:
            ctx.target_positions({"B": 200, "A": 300})
        if ctx.bar_index == 2:
            ctx.target_positions({"A": 0})
        ctx.record(index=ctx.bar_index)

    result = Backtest(data, costs=FREE).run(strategy, backend=backend)
    for ctx in saved:
        index = ctx.bar_index
        expected = {
            symbol: Position(
                symbol,
                int(result.holdings[index, col]),
                int(result.sellable[index, col]),
                int(result.holdings[index, col] + result.pending_shares[index, col])
                * int(result.close_units[index, col])
                / 10000,
                int(result.pending_shares[index, col]),
            )
            for col, symbol in enumerate(result.symbols)
        }
        assert ctx.account.positions == expected
        assert ctx.account.frozen_cash == 0
    return result, tuple(ctx.account for ctx in saved)


CASES = {
    "broker_growth": broker_growth_case,
    "legacy_snapshot": legacy_snapshot_case,
    "snapshot_minute_t0": lambda backend: minute_snapshot_case(backend, settlement=0),
    "snapshot_minute_t2": lambda backend: minute_snapshot_case(backend, settlement=2),
    "corporate_scheduled": lambda backend: daily_corporate_case(backend, scheduled=True),
    "corporate_callback": lambda backend: daily_corporate_case(backend, scheduled=False),
    "persistent_scheduled": lambda backend: minute_persistent_target_case(backend, scheduled=True),
    "persistent_callback": lambda backend: minute_persistent_target_case(backend, scheduled=False),
}

CASES.update(
    {
        f"minute_random_{seed}": lambda backend, seed=seed: minute_random_case(backend, seed)
        for seed in range(6)
    }
)


CASES.update(
    {
        f"inactive_weight_{sizing}_{rebalance}": (
            lambda backend, sizing=sizing, rebalance=rebalance: inactive_weight_case(
                backend, sizing, rebalance
            )
        )
        for sizing in ("close", "execution")
        for rebalance in (False, True)
    }
)

CASES.update(WEIGHT_CASES)


@pytest.mark.parametrize("scenario", CASES)
def test_general_runtime_review(backend, scenario):
    CASES[scenario](backend)


def error_case(backend, kind):
    action = distribution()
    quantity = 100
    if kind.startswith("merger"):
        action = distribution(kind="merger", cash_per_share=0, pay_date=None)
    elif kind == "fractional":
        action = distribution(
            bonus_per_share=".003",
            share_credit_date="2025-01-07",
            share_listing_date="2025-01-08",
            taxable_bonus_amount_per_share=0,
        )
    if kind == "merger_pending":
        quantity = 1
    data = market_with_actions([10] * 6, [action])
    observed = []

    def strategy(ctx):
        observed.append((ctx.now, ctx.account, ctx.orders, ctx.intents))
        if ctx.bar_index == 0:
            ctx.target_positions({"A": quantity})
        if kind == "callback_failure" and ctx.bar_index == 3:
            raise LookupError("review callback sentinel")

    try:
        Backtest(data, costs=FREE, execution=BarExecution()).run(strategy, backend=backend)
    except Exception as error:
        chain = []
        while error is not None:
            chain.append((type(error).__name__, str(error)))
            error = error.__cause__
        return dict(errors=chain, callback_observations=digest(observed))
    else:
        raise AssertionError(f"expected error for {kind}")


def error_manifest(backend):
    return {
        kind: error_case(backend, kind)
        for kind in ("merger_held", "merger_pending", "fractional", "callback_failure")
    }


@pytest.mark.parametrize(
    "expected", ["merger_held", "merger_pending", "fractional", "callback_failure"]
)
def test_general_runtime_error_review(backend, expected):
    observed = error_case(backend, expected)["errors"]
    if expected == "callback_failure":
        assert observed[-1] == ("LookupError", "review callback sentinel")
    elif expected.startswith("merger"):
        assert observed[0] == ("UnsupportedCorporateAction", "unsupported merger: d1")
    else:
        assert observed[0] == (
            "UnsupportedCorporateAction",
            "fractional share allocation unavailable: d1",
        )


def manifest(backend):
    cases = {}
    for name, build in CASES.items():
        result, observations = build(backend)
        field_hashes = {}
        for item in fields(result):
            value = getattr(result, item.name)
            # 源码修改必然改变引擎哈希；在下方单独保留，
            # 其余所有来源字段继续逐项比较。
            if item.name == "run_info":
                value = value.to_dict()
                value.pop("engine_sha256")
            field_hashes[item.name] = digest(value)
        cases[name] = dict(
            fields=field_hashes,
            engine_sha256=result.run_info.to_dict()["engine_sha256"],
            full_run_info=result.run_info.to_dict(),
            callback_observations=digest(observations),
            orders=len(result.orders),
            fills=len(result.fills),
        )
    return dict(backend=backend, scenarios=cases, errors=error_manifest(backend))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("python", "numba"), default="python")
    args = parser.parse_args()
    print(json.dumps(manifest(args.backend), indent=2, sort_keys=True))
