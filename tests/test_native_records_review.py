"""独立检查原生列式物化的协议、回退边界及来源信息。"""

import copy
import gc
import importlib
import os
import pickle
import sys
import weakref
from dataclasses import FrozenInstanceError, asdict, fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_general_runtime_review import CASES, canonical

from doribt.accounting.orders import Fill, IntentRecord, Order, Reason
from doribt.accounting.taxes import TaxLotRecord
from doribt.runtime import native_records as native


def extension():
    module = native._extension()
    if module is None:
        if os.environ.get("DORIBT_NATIVE_RECORDS") == "required":
            pytest.fail("required 模式缺少原生扩展")
        pytest.skip("需要独立构建的原生扩展")
    return module


@pytest.mark.parametrize("mode", ["auto", "required", "off"])
@pytest.mark.parametrize("compatible", [False, True])
def test_native_review_modes(monkeypatch, mode, compatible):
    module = SimpleNamespace(API_VERSION=1 if compatible else 99)
    monkeypatch.setattr(native, "_extension", lambda: module)
    monkeypatch.setenv("DORIBT_NATIVE_RECORDS", mode)
    if mode == "required" and not compatible:
        with pytest.raises(RuntimeError, match="原生"):
            native.available()
    else:
        assert native.available() is (compatible and mode != "off")


def test_native_review_missing_invalid_and_modified_type(monkeypatch):
    monkeypatch.setattr(native, "_extension", lambda: None)
    monkeypatch.setenv("DORIBT_NATIVE_RECORDS", "auto")
    assert not native.available()
    monkeypatch.setenv("DORIBT_NATIVE_RECORDS", "required")
    with pytest.raises(RuntimeError):
        native.available()
    monkeypatch.setenv("DORIBT_NATIVE_RECORDS", "invalid")
    with pytest.raises(ValueError):
        native.available()
    monkeypatch.setattr(native, "_extension", lambda: SimpleNamespace(API_VERSION=1))
    monkeypatch.setenv("DORIBT_NATIVE_RECORDS", "auto")
    monkeypatch.setattr(
        Fill, "__getattribute__", lambda self, key: object.__getattribute__(self, key)
    )
    assert not native.available()
    monkeypatch.setenv("DORIBT_NATIVE_RECORDS", "required")
    with pytest.raises(RuntimeError):
        native.available()


@pytest.mark.parametrize("kind", [Order, Fill, IntentRecord, TaxLotRecord])
def test_native_review_record_protocols(kind):
    module = extension()
    names = tuple(field.name for field in fields(kind))
    values = tuple(
        Reason.NONE if name == "reason" else "A" if name == "symbol" else 2**80 for name in names
    )
    columns = tuple([value, value] for value in values)
    expected = kind(*values)
    records = module.bulk_columns(kind, names, columns)
    assert type(records) is tuple
    for record in records:
        assert type(record) is kind and record == expected
        assert hash(record) == hash(expected) and repr(record) == repr(expected)
        assert asdict(record) == asdict(expected)
        assert list(record.__dict__) == list(expected.__dict__)
        assert replace(record) == expected
        assert copy.deepcopy(record) == expected
        assert pickle.loads(pickle.dumps(record)) == expected
        with pytest.raises(FrozenInstanceError):
            setattr(record, names[0], 0)
    assert records[0].__dict__ is not records[1].__dict__
    handle = weakref.ref(records[0])
    object.__setattr__(records[0], names[0], records[0])
    del records
    gc.collect()
    assert handle() is None
    assert module.bulk_columns(kind, names, tuple([] for _ in names)) == ()


@pytest.mark.parametrize("invalid", ["names", "columns", "count", "length", "iterator", "order"])
def test_native_review_invalid_columns_leave_no_references(invalid):
    module = extension()
    names = native.NAMES[Fill]
    columns = tuple([1] for _ in names)
    cases = {
        "names": (list(names), columns),
        "columns": (names, list(columns)),
        "count": (names, columns[:-1]),
        "length": (names, ([],) + columns[1:]),
        "iterator": (names, (iter([]),) + columns[1:]),
        "order": (names[::-1], columns),
    }
    args = cases[invalid]
    before = sys.getrefcount(Fill)
    for _ in range(20):
        with pytest.raises((ValueError, TypeError)):
            module.bulk_columns(Fill, *args)
    gc.collect()
    assert sys.getrefcount(Fill) == before


@pytest.mark.parametrize("scenario", CASES)
def test_native_review_full_result_matches_disabled(monkeypatch, scenario):
    extension()
    if os.environ.get("DORIBT_NATIVE_RECORDS") == "required":
        importlib.import_module("numba")
    else:
        pytest.importorskip("numba")
    monkeypatch.setenv("DORIBT_NATIVE_RECORDS", "off")
    expected, observations = CASES[scenario]("numba")
    monkeypatch.setenv("DORIBT_NATIVE_RECORDS", "required")
    actual, actual_observations = CASES[scenario]("numba")
    assert canonical(observations) == canonical(actual_observations)
    for field in fields(actual):
        if field.name != "run_info":
            assert canonical(getattr(actual, field.name)) == canonical(
                getattr(expected, field.name)
            )
    left, right = expected.run_info.to_dict(), actual.run_info.to_dict()
    assert left.pop("engine_sha256") != right.pop("engine_sha256")
    assert left == right


def test_native_review_errors_never_silently_fall_back(monkeypatch):
    extension()
    monkeypatch.setenv("DORIBT_NATIVE_RECORDS", "required")

    def fail(*args):
        raise LookupError("native construction sentinel")

    module = SimpleNamespace(API_VERSION=1, bulk_columns=fail)
    monkeypatch.setattr(native, "_extension", lambda: module)
    with pytest.raises(LookupError, match="native construction sentinel"):
        native._create(Fill, [[1] for _ in native.NAMES[Fill]])


def test_native_review_provenance_includes_c_source(monkeypatch):
    monkeypatch.setenv("DORIBT_NATIVE_RECORDS", "off")
    expected, _ = CASES["final_unsized_weight"]("python")
    original = Path.read_bytes

    def changed(path):
        content = original(path)
        return (
            content + b"\n/* review source identity */"
            if path.name == "_native_records.c"
            else content
        )

    monkeypatch.setattr(Path, "read_bytes", changed)
    actual, _ = CASES["final_unsized_weight"]("python")
    assert (
        expected.run_info.to_dict()["engine_sha256"] != actual.run_info.to_dict()["engine_sha256"]
    )


@pytest.mark.parametrize("mode", ["auto", "required", "off"])
def test_native_review_unsupported_runtime_never_imports(monkeypatch, mode):
    native._extension.cache_clear()
    monkeypatch.setenv("DORIBT_NATIVE_RECORDS", mode)
    monkeypatch.setattr(native, "_compatible_runtime", lambda: False)

    def forbidden(name):
        pytest.fail("unsupported interpreter must not import native extension")

    monkeypatch.setattr(native.importlib, "import_module", forbidden)
    try:
        if mode == "required":
            with pytest.raises(RuntimeError):
                native.available()
        else:
            assert not native.available()
    finally:
        native._extension.cache_clear()
