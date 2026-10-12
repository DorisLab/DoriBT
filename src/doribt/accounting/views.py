"""按访问需要构造持仓对象；数组快照与后续账户变化完全隔离。"""

from collections.abc import Iterator, Mapping
from types import MappingProxyType, NotImplementedType

import numpy as np

from doribt.accounting.account import Position
from doribt.kernels.execution import IntArray


class PositionView(Mapping[str, Position]):
    def __init__(
        self,
        columns: Mapping[str, int],
        quantities: IntArray,
        sellable: IntArray,
        pending: IntArray,
        prices: IntArray,
        frozen: IntArray | None = None,
    ) -> None:
        self._columns = columns
        self._values = np.stack((quantities, sellable, pending, prices))
        self._values.setflags(write=False)
        self._frozen = None if frozen is None else frozen.copy()
        self._cache: dict[str, Position] = {}

    def __len__(self) -> int:
        return len(self._columns)

    def __iter__(self) -> Iterator[str]:
        return iter(self._columns)

    def copy(self) -> dict[str, Position]:
        return dict(self.items())

    def __or__(self, other: object) -> dict[object, object] | NotImplementedType:
        if not isinstance(other, Mapping):
            return NotImplemented
        return dict(self) | dict(other)

    def __ror__(self, other: object) -> dict[object, object] | NotImplementedType:
        if not isinstance(other, Mapping):
            return NotImplemented
        return dict(other) | dict(self)

    def __reversed__(self) -> Iterator[str]:
        return reversed(tuple(self._columns))

    def __repr__(self) -> str:
        return repr(MappingProxyType(dict(self)))

    def __getitem__(self, symbol: str) -> Position:
        if symbol not in self._cache:
            column = self._columns[symbol]
            quantity, sellable, pending, price = map(int, self._values[:, column])
            self._cache[symbol] = Position(
                symbol,
                quantity,
                sellable,
                (quantity + pending) * price / 10_000,
                pending,
                0 if self._frozen is None else int(self._frozen[column]),
            )
        return self._cache[symbol]
