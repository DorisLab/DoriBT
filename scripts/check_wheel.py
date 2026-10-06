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
from doribt import (
    CorporateAction, Instrument, MarketData, RuleBook, RulePeriod, TradingRule, WeightTargets,
    PriceAdjustment, china_rules, Backtest, BarExecution, FixedTicks, PositionTargets
)
assert importlib.util.find_spec('doribt.experimental') is None

backend = sys.argv[1]
assert 'numba' not in sys.modules, 'Importing DoriBT must not import Numba'
assert 'matplotlib' not in sys.modules, 'Importing DoriBT must not import plotting dependencies'
installed = distribution('doribt')
assert doribt.__version__ == installed.version, 'Package and distribution versions must agree'
assert Path(doribt.__file__).samefile(installed.locate_file('doribt/__init__.py'))
origin = json.loads(installed.read_text('direct_url.json'))
assert 'archive_info' in origin, 'Must load a wheel, not an editable source tree'
for name, expected_hash in json.loads(sys.argv[2]).items():
    assert hashlib.sha256(installed.locate_file(name).read_bytes()).hexdigest() == expected_hash
if backend == 'python':
    assert importlib.util.find_spec('numba') is None, 'Base install unexpectedly includes Numba'
sessions = ['2025-01-02', '2025-01-03', '2025-01-06']
rule = TradingRule(price_tick='.01', buy_minimum=100, buy_step=100, sell_step=100,
                   settlement_days=1, stamp_duty_sell=0, transfer_fee=0)
data = MarketData.from_records(
    [dict(session=session, symbol='A', status='trading', open=price, high=price,
          low=price, close=price, volume=1000, upper_limit=None, lower_limit=None)
     for session, price in zip(sessions, (10, 10, 11), strict=True)],
    calendar=sessions, instruments=[Instrument(symbol='A', kind='stock')],
    rules=RuleBook((RulePeriod(symbol='A', start='2025-01-02', end='2025-01-06',
                              rule=rule, source='test', version='1'),)), source='test',
    actions=[CorporateAction(action_id='dividend', symbol='A', kind='distribution',
                             announced='2025-01-02', record_date='2025-01-03',
                             ex_date='2025-01-06', pay_date='2025-01-07',
                             cash_per_share=1, source='synthetic wheel check')],
    adjustments=[PriceAdjustment(action_id='dividend', factor='.9', known_on='2025-01-03',
                                 source='synthetic reference ratio')])
assert data.prices('close').tolist() == [[10.0], [10.0], [11.0]]
assert len(data.fingerprint) == 64
adjusted = data.prices('close', adjustment='asof', as_of='2025-01-06')[:,0]
np.testing.assert_allclose(adjusted, [9,9,11])
targets = WeightTargets(sessions=data.sessions, weights={'A': [.95, 0, 0]})
formal = doribt.Backtest(data, initial_cash=10000).run(targets, backend=backend)
np.testing.assert_array_equal(formal.equity, [10000.,9995.,11610.])
assert [fill.quantity for fill in formal.fills] == [900, -900]
assert formal.dividend_receivable[-1] == 900
assert formal.tax_payable[-1] == 180
assert formal.taxes[0].amount_units == 1_800_000
assert formal.tax_payments == ()
historical = china_rules({'A': 'sse_star'}, start='2025-01-02', end='2025-01-06')
assert historical.periods[0].rule.sell_minimum == 200
assert historical.periods[0].rule.order_maximum == 100000
assert formal.run_info.to_dict()['data']['fingerprint'] == data.fingerprint
from doribt.clock import MinuteClock
clock = MinuteClock.build(data.sessions[:1], '5min')
minutes = MarketData.from_minutes(
    [dict(timestamp=point, phase='continuous', symbol='A', status='trading',
          open=10, high=11, low=9, close=10, volume=1000, upper_limit=12, lower_limit=8)
     for point in clock.timestamps],
    calendar=data.sessions[:1], frequency='5min', instruments=data.instruments,
    rules=data.rules, source='wheel minute fixture')
minute_result = Backtest(minutes, execution=BarExecution(slippage=FixedTicks(1))).run(
    lambda ctx: ctx.order('A', 200, valid_for='day') if ctx.bar_index == 0 else None,
    backend=backend)
assert len(minute_result.orders) == 1 and len(minute_result.fills) == 4
assert minute_result.orders[0].filled == 200
assert minute_result.orders[0].commission == 5
assert minute_result.fills[0].timestamp == clock.timestamps[1]
minute_targets = PositionTargets(sessions=minutes.timeline, quantities={'A': [200]*48})
scheduled = Backtest(minutes, execution=BarExecution(slippage=FixedTicks(1))).run(
    minute_targets, backend=backend)
np.testing.assert_array_equal(scheduled.cash_units, minute_result.cash_units)
assert scheduled.run_info.to_dict()['execution_path'] == 'scheduled_segments'
assert len(scheduled.fills) == 4
output = formal.export(Path.cwd() / 'report', periods_per_year=252, plot=backend == 'numba')
manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
assert manifest['schema'] == 'doribt.export/1'
assert json.loads((output / 'stats.json').read_text())['fill_count'] == 2
for name, facts in manifest['files'].items():
    assert hashlib.sha256((output / name).read_bytes()).hexdigest() == facts['sha256']
if backend == 'numba':
    assert (output / 'equity.png').stat().st_size > 1000
if backend == 'python':
    assert importlib.util.find_spec('matplotlib') is None
    try:
        formal.plot()
    except ImportError as error:
        assert 'doribt[plot]' in str(error)
    else:
        raise AssertionError('Missing plotting dependency must be explicit')
    try:
        doribt.Backtest(data).run(targets, backend='numba')
    except ImportError as error:
        assert 'doribt[numba]' in str(error)
    else:
        raise AssertionError('Formal engine must not silently fall back either')
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
            export += ["--extra", "numba", "--extra", "plot"]
        subprocess.run(
            [*export, "--output-file", str(requirements)],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        package = str(wheel) + ("[numba,plot]" if backend == "numba" else "")
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
