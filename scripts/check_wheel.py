"""Verify an actual distribution, outside the checkout and its editable venv."""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]

SMOKE = """
import importlib.util
import hashlib
import json
import sys
from importlib.metadata import distribution
from pathlib import Path
import numpy as np
import doribt
from doribt.experimental import Backtest, CloseSignals, Costs, DailyBars

backend = sys.argv[1]
assert 'numba' not in sys.modules, 'Importing DoriBT must not import Numba'
installed = distribution('doribt')
assert Path(doribt.__file__).samefile(installed.locate_file('doribt/__init__.py'))
origin = json.loads(installed.read_text('direct_url.json'))
assert 'archive_info' in origin, 'Must load a wheel, not an editable source tree'
for name, expected_hash in json.loads(sys.argv[2]).items():
    assert hashlib.sha256(installed.locate_file(name).read_bytes()).hexdigest() == expected_hash
if backend == 'python':
    assert importlib.util.find_spec('numba') is None, 'Base install unexpectedly includes Numba'
b = DailyBars(['2025-01-02', '2025-01-03', '2025-01-06'], [10.,10.,11.],
              [10.,10.5,11.], [12.,12.,12.], [8.,8.,8.], [False,False,False])
r = Backtest(b, initial_cash=10000, costs=Costs(slippage_ticks=0)).run(
    CloseSignals(sessions=b.sessions, hold=[True,False,True]), backend=backend)
np.testing.assert_array_equal(r.equity, [10000.,10445.,10890.])
assert r.backend == backend
assert r.stats()['fill_count'] == 2
if backend == 'python':
    try:
        Backtest(b).run(CloseSignals(sessions=b.sessions, hold=[True]*3), backend='numba')
    except ImportError as error:
        assert 'doribt[numba]' in str(error)
    else:
        raise AssertionError('Missing Numba must not silently fall back')
print('Installed wheel passed:', doribt.__version__, backend)
"""


def check_wheel(wheel: Path, backend: str) -> None:
    wheel = wheel.resolve(strict=True)
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        if "doribt/py.typed" not in names or not any(
            n.endswith("/licenses/LICENSE") for n in names
        ):
            raise RuntimeError("Wheel must contain type marker and LICENSE")
        if any(n.startswith(("tests/", "data/", ".env", ".git/")) for n in names):
            raise RuntimeError("Unexpected development or data files in wheel")
        hashes = {
            n: hashlib.sha256(archive.read(n)).hexdigest() for n in names if n.startswith("doribt/")
        }
    with tempfile.TemporaryDirectory(prefix="doribt-wheel-") as temporary:
        requirements = Path(temporary) / "requirements.txt"
        export = ["uv", "export", "--locked", "--no-dev", "--no-emit-project"]
        if backend == "numba":
            export += ["--extra", "numba"]
        subprocess.run(
            [*export, "--output-file", str(requirements)],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        package = str(wheel) + ("[numba]" if backend == "numba" else "")
        subprocess.run(
            [
                "uv",
                "run",
                "--isolated",
                "--no-project",
                "--python",
                "3.13",
                "--with",
                package,
                "--with-requirements",
                str(requirements),
                "python",
                "-I",
                "-c",
                SMOKE,
                backend,
                json.dumps(hashes),
            ],
            cwd=temporary,
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--backend", choices=["python", "numba"], default="python")
    args = parser.parse_args()
    check_wheel(args.wheel, args.backend)


if __name__ == "__main__":
    main()
