"""可选记录扩展的离线构建工具；运行时不得调用本模块。"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

NATIVE_FILENAME = "_native_records.abi3.so"
LIMITED_API = "0x030C0000"


class NativeBuildError(RuntimeError):
    """显式请求的原生构建未能完成，禁止悄悄退回纯 Python。"""


def native_requested() -> bool:
    """未设置或设为 off／0 时仅构建纯 Python 包。"""
    value = os.environ.get("DORIBT_BUILD_NATIVE", "0")
    if value in ("", "0", "off"):
        return False
    if value == "required":
        return True
    raise NativeBuildError("DORIBT_BUILD_NATIVE 只能设置为 required、off 或 0（默认）。")


def native_wheel_tag() -> str:
    """CPython 3.13—3.15 的 GIL 构建共享稳定 ABI，平台限 Linux x86_64。"""
    if sys.implementation.name != "cpython" or not (3, 13) <= sys.version_info[:2] < (3, 16):
        raise NativeBuildError("原生构建支持 CPython 3.13—3.15；请使用默认纯 Python 构建。")
    if sys.platform != "linux" or sysconfig.get_platform() != "linux-x86_64":
        raise NativeBuildError("原生构建目前仅验证 Linux x86_64；不声明其他平台兼容。")
    if sysconfig.get_config_var("Py_GIL_DISABLED") or sysconfig.get_config_var("Py_DEBUG"):
        raise NativeBuildError("原生构建不支持 free-threaded 或 debug Python。")
    return "cp313-abi3-linux_x86_64"


def _header_version(path: Path) -> tuple[int, int]:
    text = (path / "patchlevel.h").read_text(encoding="utf-8")
    numbers = []
    for part in ("MAJOR", "MINOR"):
        match = re.search(rf"^\s*#define\s+PY_{part}_VERSION\s+(\d+)\s*$", text, re.M)
        if match is None:
            raise NativeBuildError(f"无法读取 Python 头文件版本：{path}")
        numbers.append(int(match.group(1)))
    return numbers[0], numbers[1]


def _check_headers(path: Path) -> Path:
    try:
        if not (path / "Python.h").is_file():
            raise NativeBuildError(f"目录缺少 Python.h：{path}")
        if not (3, 12) <= _header_version(path) < (3, 16):
            raise NativeBuildError("原生构建需要 Python 3.12—3.15 稳定 ABI 头文件。")
        config = (path / "pyconfig.h").read_text(encoding="utf-8")
    except OSError as error:
        raise NativeBuildError(f"无法读取 Python 开发头文件：{path}") from error
    if re.search(r"^\s*#define\s+(Py_GIL_DISABLED|Py_DEBUG)\s+1\s*$", config, re.M):
        raise NativeBuildError("不支持 free-threaded 或 debug Python 头文件。")
    return path.resolve()


def native_include() -> Path:
    """只读取本机头文件；不下载、不自动安装开发依赖。"""
    override = os.environ.get("DORIBT_NATIVE_INCLUDE")
    candidate = Path(override) if override else Path(sysconfig.get_path("include"))
    try:
        return _check_headers(candidate)
    except NativeBuildError as error:
        raise NativeBuildError(
            f"{error}。请安装开发头文件或设置 DORIBT_NATIVE_INCLUDE；"
            "不需要原生扩展时设置 DORIBT_BUILD_NATIVE=0。"
        ) from error


def _run(command: list[str], purpose: str) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise NativeBuildError(f"{purpose}失败，未找到命令：{command[0]}") from error
    except subprocess.CalledProcessError as error:
        raise NativeBuildError(f"{purpose}失败：\n{error.stderr or error.stdout}") from error
    except OSError as error:
        raise NativeBuildError(f"{purpose}失败：{error}") from error


def _verify_extension(path: Path) -> None:
    # 新进程从指定产物加载，避免源码目录、旧二进制与可编辑安装掩盖构建失败。
    check = (
        "import importlib.util, sys; "
        "s = importlib.util.spec_from_file_location('_native_records', sys.argv[1]); "
        "assert s is not None and s.loader is not None; "
        "m = importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        "assert m.API_VERSION == 1 and callable(m.bulk_columns)"
    )
    _run([sys.executable, "-I", "-c", check, str(path)], "原生扩展加载检查")


def build_native(source: Path, output_dir: Path) -> Path:
    """显式构建并验证扩展；失败直接抛错，不生成伪原生 wheel。"""
    native_wheel_tag()
    include = native_include()
    if not source.is_file():
        raise NativeBuildError(f"缺少原生扩展源码：{source}")
    compiler = shlex.split(os.environ.get("CC", "cc"))
    if not compiler:
        raise NativeBuildError("CC 不能为空；需要可用的 C11 编译器。")
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir.resolve() / NATIVE_FILENAME
    with tempfile.TemporaryDirectory(prefix=".doribt-native-", dir=output_dir) as temporary:
        artifact = Path(temporary).resolve() / NATIVE_FILENAME
        command = [
            *compiler,
            "-shared",
            "-fPIC",
            "-O3",
            "-std=c11",
            "-fno-strict-aliasing",
            f"-DPy_LIMITED_API={LIMITED_API}",
            "-I",
            str(include),
            str(source.resolve()),
            "-o",
            str(artifact),
        ]
        _run(command, "原生扩展编译")
        _verify_extension(artifact)
        artifact.replace(destination)
    return destination
