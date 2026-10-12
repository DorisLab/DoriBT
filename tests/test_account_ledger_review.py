"""使用独立列表模型验证数组账户的 FIFO 与交收事件堆。"""

from datetime import date, timedelta

import numpy as np
import pytest

from doribt.accounting.account import Account, Lot


@pytest.mark.parametrize("seed", range(12))
def test_review_array_lots_against_plain_fifo_model(seed):
    rng = np.random.default_rng(seed)
    symbols = ("A", "B", "C")
    account = Account(10000, symbols)
    model = []
    start = date(2025, 1, 2)
    for step in range(240):
        index = step // 4
        symbol = symbols[int(rng.integers(3))]
        available = sum(q for s, q, _, at, _ in model if s == symbol and at <= index)
        if available and rng.random() < 0.45:
            quantity = int(rng.integers(1, available + 1))
            account.apply_fill(symbol, -quantity, start + timedelta(days=index), 100000, index, 0)
            remaining = quantity
            for lot in model:
                if lot[0] == symbol and lot[3] <= index:
                    consumed = min(remaining, lot[1])
                    lot[1] -= consumed
                    remaining -= consumed
            model = [lot for lot in model if lot[1]]
        else:
            quantity = int(rng.integers(1, 400))
            # 当日可卖批次可以排在长期锁定的旧批次之后。
            available = index + int(rng.choice([0, 1, 2, 5, 20]))
            acquired = start + timedelta(days=index)
            price = int(rng.integers(1, 200000))
            account.add_lot(Lot(symbol, quantity, acquired, available, price))
            model.append([symbol, quantity, acquired, available, price])
        expected = [sum(q for s, q, *_ in model if s == symbol) for symbol in symbols]
        assert account.quantities().tolist() == expected
        # 任意日期查询包括未来交收后的回退；查询不得改变
        # 当前存活批次数量或 FIFO 顺序。
        for day in (index, index + 25, max(0, index - 3), index):
            expected = [
                sum(q for s, q, _, at, _ in model if s == symbol and at <= day)
                for symbol in symbols
            ]
            assert account.quantities(day).tolist() == expected
        assert [
            [lot.symbol, lot.quantity, lot.acquired, lot.available_session, lot.price_units]
            for lot in account.lots
        ] == model
        # 返回数组不能引用内部汇总缓存。
        account.quantities()[:] = -999
        account.quantities(index)[:] = -999
