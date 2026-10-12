"""独立复核：扩容时旧委托引用、快照及支出上限不能丢失。"""

from minute_fixtures import minute_data

from doribt import Backtest, BarExecution, Costs


def broker_growth_case(backend):
    data = minute_data(days=3, frequency="5min", volume=100, settlement=0)
    snapshots = []

    def strategy(ctx):
        if ctx.bar_index == 0:
            for index in range(90):
                ctx.order("A", 100, valid_for="day", max_spend=1000 + index)
            snapshots.append(ctx.orders)
        if ctx.bar_index == 4:
            snapshots.append(ctx.orders)
            for order_id in range(70, 80):
                ctx.cancel_order(order_id)
        if ctx.bar_index == 10:
            for _ in range(75):
                ctx.order("A", -100, valid_for="day")
            snapshots.append(ctx.orders)
        if ctx.bar_index == 48:
            ctx.order("A", 7000, valid_for="day")
        if ctx.bar_index == 143:
            ctx.order("A", 100)
            snapshots.append(ctx.orders)

    result = Backtest(
        data,
        initial_cash=100000,
        costs=Costs(commission=0, minimum_commission=0),
        execution=BarExecution(participation=1),
    ).run(strategy, backend=backend)
    assert len(result.orders) == 167
    assert result.orders[-1].status == "unexecuted"
    assert len(snapshots[0]) == 90
    assert all(order.filled == 0 for order in snapshots[0])
    assert all(order.status == "cancelled" for order in result.orders[69:79])
    assert any(order.filled < 0 for order in result.orders)
    assert result.holdings.min() >= 0
    assert result.reserved_cash_units.min() >= 0
    return result, snapshots
