"""Install the built wheel in an isolated uv environment and check the base API."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
wheels = list((ROOT / "dist").glob("doribt-*.whl"))
if len(wheels) != 1:
    raise SystemExit("Expected exactly one built DoriBT wheel in dist/")
code = """
import sys
import numpy as np
import doribt
from doribt.experimental import DailyBars, Config, backtest
assert 'numba' not in sys.modules
b = DailyBars(np.array(['2025-01-02','2025-01-03']), np.array([10.,11.]),
              np.array([10.5,11.]), np.array([12.,12.]), np.array([8.,8.]),
              np.array([False,False]))
r = backtest(b, [1,0], Config(initial_cash=10000,slippage_ticks=0))
assert r.equity[:,0].tolist() == [10445.,10890.]
assert r.backend == 'python'
print('Installed wheel smoke passed:', doribt.__version__)
"""
subprocess.run(
    [
        "uv",
        "run",
        "--isolated",
        "--no-project",
        "--python",
        "3.13",
        "--with",
        str(wheels[0]),
        "python",
        "-I",
        "-c",
        code,
    ],
    cwd=ROOT,
    check=True,
)
