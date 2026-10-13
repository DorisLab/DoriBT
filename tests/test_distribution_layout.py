"""发行包排除工程历史，但保留源码构建与原生构建的必要输入。"""

import os
import sys
import tarfile
from zipfile import ZipFile

import pytest

from scripts.check_native_package import (
    ENGINEERING_SENTINEL,
    ROOT,
    _inspect_wheel,
    _one_file,
    _run,
    _sdist,
)

REQUIRED_SOURCE = (
    "pyproject.toml",
    "hatch_build.py",
    "README.md",
    "LICENSE",
    "src/doribt/__init__.py",
    "src/doribt/py.typed",
    "src/doribt/_native_build.py",
    "src/doribt/_native_records.c",
    "scripts/build_native.py",
)


def source_names(artifact):
    with tarfile.open(artifact) as archive:
        return {name.split("/", 1)[1] for name in archive.getnames() if "/" in name}


def test_seeded_engineering_is_excluded_from_sdist_and_rebuilt_wheel(tmp_path):
    env = {**os.environ, "DORIBT_BUILD_NATIVE": "off", "PYTHONUTF8": "1"}
    uv = ["uv", "--offline"]
    unpacked = _sdist(tmp_path, uv, env)
    assert (tmp_path / "source" / ENGINEERING_SENTINEL).is_file()
    names = source_names(_one_file(tmp_path / "sdist", "*.tar.gz"))
    assert not any(name == "engineering" or name.startswith("engineering/") for name in names)
    assert set(REQUIRED_SOURCE) <= names
    _run([*uv, "build", "--wheel", "--out-dir", str(tmp_path / "wheel")], unpacked, env)
    wheel = _one_file(tmp_path / "wheel", "*.whl")
    assert _inspect_wheel(wheel, False)["record_verified"] is True
    with ZipFile(wheel) as archive:
        assert not any("engineering" in name.split("/") for name in archive.namelist())
        for name in ("__init__.py", "_native_build.py", "_native_records.c", "py.typed"):
            assert archive.read("doribt/" + name) == (ROOT / "src/doribt" / name).read_bytes()


def test_actual_repository_sdist_keeps_engineering_outside_distribution(tmp_path):
    assert (ROOT / "engineering/publishing.md").is_file()
    assert (ROOT / "engineering/history").is_dir()
    env = {**os.environ, "DORIBT_BUILD_NATIVE": "off", "PYTHONUTF8": "1"}
    _run(["uv", "--offline", "build", "--sdist", "--out-dir", str(tmp_path)], ROOT, env)
    names = source_names(_one_file(tmp_path, "*.tar.gz"))
    assert not any(name == "engineering" or name.startswith("engineering/") for name in names)
    assert set(REQUIRED_SOURCE) <= names


def test_build_subprocess_preserves_utf8_error_and_nonzero_exit(tmp_path):
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    command = [
        sys.executable,
        "-c",
        "import sys; print('构建标准输出'); "
        "print('构建错误：工程路径校验失败', file=sys.stderr); sys.exit(17)",
    ]
    with pytest.raises(RuntimeError, match="退出码 17") as error:
        _run(command, tmp_path, env)
    message = str(error.value)
    assert "构建错误：工程路径校验失败" in message
    assert "构建标准输出" in message
