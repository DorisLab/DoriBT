import importlib.util
from pathlib import Path

import numpy as np


def test_sma_signal_uses_only_completed_sessions():
    path = Path(__file__).parents[1] / "examples" / "sma.py"
    spec = importlib.util.spec_from_file_location("sma_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    close = np.arange(1, 61, dtype=float)
    original = module.sma_regime(close)
    close[30:] *= 0.01
    changed = module.sma_regime(close)
    np.testing.assert_array_equal(original[:31], changed[:31])
