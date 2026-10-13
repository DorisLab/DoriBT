"""数值记录表的几何扩容，保持有效行及编号顺序。"""

import numpy as np

from doribt.kernels.execution import IntArray


def grow_table(rows: IntArray, used: int, extra: int) -> IntArray:
    needed = used + extra
    if needed <= len(rows):
        return rows
    result = np.zeros((max(needed, len(rows) * 2), rows.shape[1]), dtype=np.int64)
    result[:used] = rows[:used]
    return result


def grow_vector(values: IntArray, used: int, extra: int) -> IntArray:
    needed = used + extra
    if needed <= len(values):
        return values
    result = np.zeros(max(needed, len(values) * 2), dtype=np.int64)
    result[:used] = values[:used]
    return result
