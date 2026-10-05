"""Array types at the Python / compiled-kernel boundary."""

import numpy as np
from numpy.typing import NDArray

type FloatArray = NDArray[np.float64]
type IntArray = NDArray[np.int64]
type FlagArray = NDArray[np.int8]
type BoolArray = NDArray[np.bool_]
type DateArray = NDArray[np.datetime64]
type RecordArray = NDArray[np.void]
type MarketArrays = tuple[IntArray, IntArray, IntArray, IntArray, BoolArray]
type KernelOutput = tuple[IntArray, IntArray, IntArray, IntArray, FlagArray]
