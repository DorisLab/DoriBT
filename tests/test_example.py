import importlib.util
from pathlib import Path

import numpy as np
import pytest


def test_sma_signal_uses_only_completed_sessions():
    path = Path(__file__).parents[1] / "examples" / "sma.py"
    spec = importlib.util.spec_from_file_location("sma_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    close = np.arange(1, 61, dtype=float)
    original = module.sma_hold(close)
    close[30:] *= 0.01
    changed = module.sma_hold(close)
    np.testing.assert_array_equal(original[:30], changed[:30])
    with pytest.raises(ValueError, match="windows"):
        module.sma_hold(close, fast=20, slow=5)


def test_readme_python_example_is_executable():
    text = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    snippet = text.split("```python\n", 1)[1].split("```", 1)[0]
    namespace = {}
    exec(compile(snippet, "README.md", "exec"), namespace)
    result = namespace["result"]
    assert result.equity[0] == 100000
    assert result.equity[-1] == 116025.76
    assert len(result.fills) == 1
