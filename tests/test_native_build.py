"""可选构建边界：默认无需编译器，required 的失败不得隐式降级。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from doribt import _native_build as native


def _headers(path: Path, minor: int = 12, config: str = "") -> Path:
    path.mkdir()
    (path / "Python.h").write_text("/* 测试头文件 */", encoding="utf-8")
    (path / "patchlevel.h").write_text(
        f"#define PY_MAJOR_VERSION 3\n#define PY_MINOR_VERSION {minor}\n", encoding="utf-8"
    )
    (path / "pyconfig.h").write_text(config, encoding="utf-8")
    return path


def test_default_and_forced_pure_do_not_inspect_compiler_or_headers(monkeypatch):
    monkeypatch.delenv("DORIBT_BUILD_NATIVE", raising=False)
    monkeypatch.setenv("CC", "/不存在的编译器")
    monkeypatch.setenv("DORIBT_NATIVE_INCLUDE", "/不存在的头文件")
    assert not native.native_requested()
    monkeypatch.setenv("DORIBT_BUILD_NATIVE", "0")
    assert not native.native_requested()
    monkeypatch.setenv("DORIBT_BUILD_NATIVE", "off")
    assert not native.native_requested()
    monkeypatch.setenv("DORIBT_BUILD_NATIVE", "required")
    assert native.native_requested()


@pytest.mark.parametrize("value", ["true", "1", "auto", "Required", "false"])
def test_misspelled_build_mode_is_an_error(monkeypatch, value):
    monkeypatch.setenv("DORIBT_BUILD_NATIVE", value)
    with pytest.raises(native.NativeBuildError, match="DORIBT_BUILD_NATIVE"):
        native.native_requested()


@pytest.mark.parametrize("minor", [12, 13, 14, 15])
def test_explicit_stable_abi_headers(monkeypatch, tmp_path, minor):
    headers = _headers(tmp_path / "headers", minor)
    monkeypatch.setenv("DORIBT_NATIVE_INCLUDE", str(headers))
    assert native.native_include() == headers.resolve()


@pytest.mark.parametrize("minor", [11, 16])
def test_unsupported_headers_are_rejected(monkeypatch, tmp_path, minor):
    headers = _headers(tmp_path / "headers", minor)
    monkeypatch.setenv("DORIBT_NATIVE_INCLUDE", str(headers))
    with pytest.raises(native.NativeBuildError, match="3.12—3.15"):
        native.native_include()


@pytest.mark.parametrize("macro", ["Py_GIL_DISABLED", "Py_DEBUG"])
def test_incompatible_header_configuration_fails(monkeypatch, tmp_path, macro):
    headers = _headers(tmp_path / "headers", config=f"#define {macro} 1\n")
    monkeypatch.setenv("DORIBT_NATIVE_INCLUDE", str(headers))
    with pytest.raises(native.NativeBuildError, match="free-threaded"):
        native.native_include()


def test_missing_headers_explain_explicit_override(monkeypatch, tmp_path):
    monkeypatch.setenv("DORIBT_NATIVE_INCLUDE", str(tmp_path / "missing"))
    with pytest.raises(native.NativeBuildError, match="DORIBT_NATIVE_INCLUDE"):
        native.native_include()


def test_broken_header_version_is_not_accepted(monkeypatch, tmp_path):
    headers = _headers(tmp_path / "headers")
    (headers / "patchlevel.h").write_text("#define PY_MAJOR_VERSION 3\n", encoding="utf-8")
    monkeypatch.setenv("DORIBT_NATIVE_INCLUDE", str(headers))
    with pytest.raises(native.NativeBuildError, match="无法读取"):
        native.native_include()


def test_other_python_implementation_fails(monkeypatch):
    monkeypatch.setattr(native.sys.implementation, "name", "pypy")
    with pytest.raises(native.NativeBuildError, match="CPython 3.13"):
        native.native_wheel_tag()


@pytest.mark.parametrize("version", [(3, 12), (3, 16)])
def test_other_python_version_fails(monkeypatch, version):
    monkeypatch.setattr(native.sys, "version_info", version)
    with pytest.raises(native.NativeBuildError, match="CPython 3.13"):
        native.native_wheel_tag()


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_unsupported_platform_is_explicit(monkeypatch, platform):
    monkeypatch.setattr(native.sys, "platform", platform)
    with pytest.raises(native.NativeBuildError, match="Linux x86_64"):
        native.native_wheel_tag()


def test_unverified_architecture_is_not_tagged(monkeypatch):
    monkeypatch.setattr(native.sysconfig, "get_platform", lambda: "linux-aarch64")
    with pytest.raises(native.NativeBuildError, match="Linux x86_64"):
        native.native_wheel_tag()


@pytest.mark.parametrize("macro", ["Py_GIL_DISABLED", "Py_DEBUG"])
def test_incompatible_runtime_configuration_fails(monkeypatch, macro):
    monkeypatch.setattr(native.sys, "platform", "linux")
    monkeypatch.setattr(native.sysconfig, "get_platform", lambda: "linux-x86_64")
    monkeypatch.setattr(native.sysconfig, "get_config_var", lambda key: int(key == macro))
    with pytest.raises(native.NativeBuildError, match="free-threaded"):
        native.native_wheel_tag()


def test_missing_compiler_fails_without_output(monkeypatch, tmp_path):
    monkeypatch.setattr(native, "native_wheel_tag", lambda: "cp313-abi3-linux_x86_64")
    headers = _headers(tmp_path / "headers")
    source = tmp_path / "source.c"
    source.write_text("/* 不执行编译 */", encoding="utf-8")
    monkeypatch.setenv("DORIBT_NATIVE_INCLUDE", str(headers))
    monkeypatch.setenv("CC", str(tmp_path / "missing-cc"))
    with pytest.raises(native.NativeBuildError, match="未找到命令"):
        native.build_native(source, tmp_path / "output")
    assert not list((tmp_path / "output").iterdir())


def test_compiler_failure_preserves_diagnostic(monkeypatch, tmp_path):
    monkeypatch.setattr(native, "native_wheel_tag", lambda: "cp313-abi3-linux_x86_64")
    headers = _headers(tmp_path / "headers")
    source = tmp_path / "source.c"
    source.write_text("/* 不执行编译 */", encoding="utf-8")
    monkeypatch.setenv("DORIBT_NATIVE_INCLUDE", str(headers))

    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr="编译器诊断")

    monkeypatch.setattr(native.subprocess, "run", fail)
    with pytest.raises(native.NativeBuildError, match="编译器诊断"):
        native.build_native(source, tmp_path / "output")
    assert not list((tmp_path / "output").iterdir())


def test_build_tool_can_load_without_package_or_numpy():
    path = Path(native.__file__).resolve()
    check = (
        "import runpy, sys; runpy.run_path(sys.argv[1]); "
        "assert 'numpy' not in sys.modules; assert 'doribt' not in sys.modules"
    )
    subprocess.run([sys.executable, "-I", "-c", check, str(path)], check=True)
