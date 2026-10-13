"""隔离验证 sdist → 原生／纯 Python wheel、RECORD 及全新安装的实际执行路径。"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from importlib.metadata import version
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
BINARY_SUFFIXES = (".so", ".pyd", ".dll", ".dylib", ".o", ".a")
NATIVE_NAME = "doribt/_native_records.abi3.so"
ENGINEERING_SENTINEL = "engineering/history/package-exclusion-sentinel.json"

SMOKE = """
import importlib.util, json, os, sys
from dataclasses import asdict
from datetime import date
from importlib.metadata import distribution
from pathlib import Path
import numpy as np
import doribt
from doribt import (
    Backtest, BarExecution, Costs, Instrument, MarketData, MinuteClock, PositionTargets,
    RuleBook, RulePeriod, RunConfig, TradingRule,
)
from doribt.runtime import native_records

expected = sys.argv[1] == 'native'
installed = distribution('doribt')
package = Path(doribt.__file__).resolve()
assert package.is_relative_to(Path(sys.prefix).resolve())
assert package.samefile(installed.locate_file('doribt/__init__.py'))
origin = json.loads(installed.read_text('direct_url.json'))
assert 'archive_info' in origin and origin['url'].endswith('.whl')
assert 'doribt._native_build' not in sys.modules
assert (importlib.util.find_spec('doribt._native_records') is not None) == expected
assert native_records.available() == expected
calls = []
if expected:
    import doribt._native_records as extension
    assert extension.API_VERSION == 1
    assert Path(extension.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    original = extension.bulk_columns
    def observed(*args):
        calls.append(args[0].__name__)
        return original(*args)
    extension.bulk_columns = observed
else:
    os.environ['DORIBT_NATIVE_RECORDS'] = 'required'
    try:
        native_records.available()
    except RuntimeError:
        pass
    else:
        raise AssertionError('纯 Python wheel 必须拒绝 required 原生运行')
    os.environ['DORIBT_NATIVE_RECORDS'] = 'auto'

sessions = [date(2025, 1, 2)]
clock = MinuteClock.build(sessions, '5min')
rule = TradingRule(price_tick='.01', buy_minimum=100, buy_step=100, sell_step=100,
                   settlement_days=0, stamp_duty_sell=0, transfer_fee=0)
data = MarketData.from_minutes(
    [dict(timestamp=point, phase='continuous', symbol='A', status='trading', open=p, high=p, low=p,
          close=p, volume=10000, upper_limit=None, lower_limit=None)
     for point, p in zip(clock.timestamps, [10, 10] + [11] * 46, strict=True)],
    calendar=sessions, frequency='5min', instruments=[Instrument(symbol='A', kind='etf')],
    rules=RuleBook((RulePeriod(symbol='A', start=sessions[0], end=sessions[-1],
                              rule=rule, source='安装验证', version='1'),)),
    source='仅合成行情')
config = RunConfig(initial_cash=10000, costs=Costs(commission=0, minimum_commission=0),
                   execution=BarExecution(participation=1),
                   backend='numba' if expected else 'python')
targets = PositionTargets(sessions=data.timeline, quantities={'A': [900] + [0] * 45 + [100] * 2})
result = Backtest(data, config=config).run(targets)
assert [fill.quantity for fill in result.fills] == [900, -900, 100]
np.testing.assert_array_equal(result.equity, [10000, 10000] + [10900] * 46)
assert bool(calls) == expected
if expected:
    assert all(getattr(result, name) for name in ('orders', 'intents', 'fills', 'tax_lots'))
    assert sorted(calls) == ['Fill', 'IntentRecord', 'Order', 'TaxLotRecord']
    os.environ['DORIBT_NATIVE_RECORDS'] = 'off'
    reference = Backtest(data, config=config).run(targets)
    for name in ('orders', 'intents', 'fills', 'tax_lots'):
        assert getattr(reference, name) == getattr(result, name)
    for name in ('equity_units', 'cash_units', 'holdings', 'sellable'):
        np.testing.assert_array_equal(getattr(reference, name), getattr(result, name))
    assert (reference.run_info.to_dict()['engine_sha256'] !=
            result.run_info.to_dict()['engine_sha256'])
for records in (result.orders, result.fills, result.intents, result.tax_lots):
    for record in records:
        assert record == type(record)(**asdict(record))
print(json.dumps({'installed_from_wheel': True, 'native': expected,
                  'native_calls': calls, 'final_equity': float(result.equity[-1]),
                  'python': sys.executable, 'installation_root': sys.prefix}))
"""


def _run(command: list[str], cwd: Path, env: dict[str, str]) -> str:
    completed = subprocess.run(
        command, cwd=cwd, env=env, text=True, encoding="utf-8", capture_output=True
    )
    if completed.returncode:
        raise RuntimeError(
            f"子进程验证失败（退出码 {completed.returncode}）：\n"
            f"{completed.stderr}\n{completed.stdout}"
        )
    return completed.stdout.strip()


def _copy_source(destination: Path) -> None:
    destination.mkdir()
    for name in ("src", "scripts"):
        shutil.copytree(
            ROOT / name,
            destination / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.so", "*.pyd", "*.o", "*.a"),
        )
    for name in ("pyproject.toml", "hatch_build.py", "README.md", "LICENSE", ".gitignore"):
        shutil.copy2(ROOT / name, destination / name)
    sentinel = destination / ENGINEERING_SENTINEL
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text('{"engineering_only": true}\n', encoding="utf-8")
    _plant_stale_artifacts(destination)


def _plant_stale_artifacts(source: Path) -> None:
    for suffix in BINARY_SUFFIXES:
        (source / "src/doribt" / f"_stale_native{suffix}").write_bytes(b"stale-not-a-library")
    (source / "src/doribt/_native_records.abi3.so").write_bytes(b"stale-not-a-library")


def _one_file(path: Path, pattern: str) -> Path:
    artifacts = list(path.glob(pattern))
    if len(artifacts) != 1:
        raise AssertionError(f"预期一个新产物：{path}/{pattern}，实际 {artifacts}")
    return artifacts[0]


def _sdist(temporary: Path, uv: list[str], env: dict[str, str]) -> Path:
    source = temporary / "source"
    _copy_source(source)
    _run([*uv, "build", "--sdist", "--out-dir", str(temporary / "sdist")], source, env)
    artifact = _one_file(temporary / "sdist", "*.tar.gz")
    unpacked = temporary / "unpacked"
    with tarfile.open(artifact) as archive:
        names = [name.split("/", 1)[1] for name in archive.getnames() if "/" in name]
        assert not any(name.endswith(BINARY_SUFFIXES) for name in names)
        assert not any("engineering" in Path(name).parts for name in names)
        for required in (
            "hatch_build.py",
            "src/doribt/_native_build.py",
            "src/doribt/_native_records.c",
            "scripts/build_native.py",
        ):
            assert required in names, f"sdist 缺少 {required}"
        archive.extractall(unpacked, filter="data")
    roots = list(unpacked.iterdir())
    assert len(roots) == 1
    _plant_stale_artifacts(roots[0])
    return roots[0]


def _check_record(archive: ZipFile, record_path: str) -> None:
    rows = list(csv.reader(io.StringIO(archive.read(record_path).decode("utf-8"))))
    assert {row[0] for row in rows} == set(archive.namelist())
    assert len(rows) == len(archive.namelist())
    for name, digest, size in rows:
        if name == record_path:
            assert digest == size == ""
            continue
        content = archive.read(name)
        expected = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
        assert digest == f"sha256={expected}" and int(size) == len(content)


def _inspect_wheel(wheel: Path, native: bool) -> dict[str, object]:
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert not any("engineering" in Path(name).parts for name in names)
        binaries = [name for name in names if name.endswith(BINARY_SUFFIXES)]
        assert binaries == ([NATIVE_NAME] if native else [])
        wheel_path = next(name for name in names if name.endswith(".dist-info/WHEEL"))
        record_path = next(name for name in names if name.endswith(".dist-info/RECORD"))
        metadata = archive.read(wheel_path).decode("utf-8")
        tag = "cp313-abi3-linux_x86_64" if native else "py3-none-any"
        assert f"Root-Is-Purelib: {'false' if native else 'true'}" in metadata
        assert f"Tag: {tag}\n" in metadata and wheel.name.endswith(f"-{tag}.whl")
        assert "doribt/py.typed" in names
        assert "doribt/_native_records.c" in names
        _check_record(archive, record_path)
        binary_hash = hashlib.sha256(archive.read(NATIVE_NAME)).hexdigest() if native else None
    return {
        "wheel": wheel.name,
        "wheel_path": str(wheel),
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "native_sha256": binary_hash,
        "record_verified": True,
        "tag": tag,
    }


def _fresh_install(
    wheel: Path, temporary: Path, uv: list[str], env: dict[str, str], native: bool
) -> dict[str, object]:
    target = temporary / ("native-install" if native else "pure-install")
    _run([*uv, "venv", "--python", sys.executable, str(target)], temporary, env)
    python = target / "bin/python"
    dependencies = [f"numpy=={version('numpy')}"]
    if native:
        dependencies += [f"numba=={version('numba')}", f"llvmlite=={version('llvmlite')}"]
    _run(
        [*uv, "pip", "install", "--python", str(python), str(wheel), *dependencies],
        temporary,
        env,
    )
    mode = "native" if native else "pure"
    smoke_env = {**env, "DORIBT_NATIVE_RECORDS": "required" if native else "auto"}
    result = _run([str(python), "-I", "-c", SMOKE, mode], temporary, smoke_env)
    details: dict[str, object] = json.loads(result)
    return details


def check(uv: list[str], temporary: Path) -> list[dict[str, object]]:
    env = dict(os.environ)
    pure_env = {
        **env,
        "DORIBT_BUILD_NATIVE": "0",
        "CC": str(temporary / "missing-compiler"),
        "DORIBT_NATIVE_INCLUDE": str(temporary / "missing-headers"),
    }
    source = _sdist(temporary, uv, pure_env)
    results = []
    for native in (False, True):
        output = temporary / ("native-wheel" if native else "pure-wheel")
        build_env = {**env, "DORIBT_BUILD_NATIVE": "required"} if native else pure_env
        _run([*uv, "build", "--wheel", "--out-dir", str(output)], source, build_env)
        wheel = _one_file(output, "*.whl")
        inspected = _inspect_wheel(wheel, native)
        inspected["smoke"] = _fresh_install(wheel, temporary, uv, build_env, native)
        results.append(inspected)
    failure = subprocess.run(
        [*uv, "build", "--wheel", "--out-dir", str(temporary / "must-fail")],
        cwd=source,
        env={**env, "DORIBT_BUILD_NATIVE": "required", "CC": pure_env["CC"]},
        capture_output=True,
        text=True,
    )
    assert failure.returncode != 0 and not list((temporary / "must-fail").glob("*.whl"))
    assert "未找到命令" in failure.stderr
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="只使用已有 uv 缓存")
    parser.add_argument("--report", type=Path, help="保存 JSON 验证凭据")
    parser.add_argument("--work-dir", type=Path, help="保留全部产物与独立安装；目录必须尚不存在")
    args = parser.parse_args()
    uv = ["uv", "--offline"] if args.offline else ["uv"]
    if args.work_dir:
        work = args.work_dir.resolve()
        work.mkdir(parents=True, exist_ok=False)
        results = check(uv, work)
    else:
        with tempfile.TemporaryDirectory(prefix="doribt-native-packaging-") as temporary:
            results = check(uv, Path(temporary))
    report = json.dumps(
        {"sdist_verified": True, "required_failure_verified": True, "wheels": results},
        ensure_ascii=False,
        indent=2,
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
