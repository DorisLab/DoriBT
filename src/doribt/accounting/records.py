"""仅供已验证数值输出使用的不可变记录工厂，公开构造器保持原样。"""

from collections.abc import Callable
from dataclasses import MISSING, fields
from functools import cache
from typing import Any, cast

from doribt.accounting.orders import Fill, IntentRecord, Order
from doribt.accounting.taxes import TaxLotRecord


def _plain_record(kind: type[object]) -> bool:
    if kind not in (Order, Fill, IntentRecord, TaxLotRecord):
        return False
    if hasattr(kind, "__post_init__") or hasattr(kind, "__slots__"):
        return False
    initializer = getattr(kind.__init__, "__code__", None)
    if initializer is None or initializer.co_filename != "<string>":
        return False
    return all(field.init and field.default_factory is MISSING for field in fields(cast(Any, kind)))


@cache
def record_factory[T](kind: type[T]) -> Callable[[tuple[object, ...]], T]:
    constructor = cast(Callable[..., T], kind)
    if not _plain_record(kind):
        return lambda values: constructor(*values)
    names = tuple(field.name for field in fields(cast(Any, kind)))
    size = len(names)

    def create(values: tuple[object, ...]) -> T:
        if len(values) != size:
            return constructor(*values)
        # 更新独立实例字典以保留共享键布局；不延迟或省略公开记录。
        result = object.__new__(kind)
        result.__dict__.update(zip(names, values, strict=True))
        return result

    return create
