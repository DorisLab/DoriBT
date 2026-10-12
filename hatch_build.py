"""Hatchling 构建钩子：默认纯 Python，显式 required 才编译记录扩展。"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path
from typing import Any, Protocol, cast

from hatchling.builders.config import BuilderConfig
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class _NativeBuilder(Protocol):
    def native_requested(self) -> bool: ...

    def native_wheel_tag(self) -> str: ...

    def build_native(self, source: Path, output_dir: Path) -> Path: ...


def _load_builder(root: Path) -> _NativeBuilder:
    # 构建隔离环境只装 Hatchling，不导入依赖 NumPy 的 doribt 包。
    path = root / "src/doribt/_native_build.py"
    spec = importlib.util.spec_from_file_location("_doribt_native_build", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载原生构建工具：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(_NativeBuilder, module)


class NativeRecordsBuildHook(BuildHookInterface[BuilderConfig]):
    """仅把本次构建的临时产物装入 wheel，绝不复用源码树中的 .so。"""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        builder = _load_builder(Path(self.root))
        if not builder.native_requested():
            return
        if version != "standard":
            raise RuntimeError(
                "required 原生构建仅支持普通 wheel；开发时请显式运行 scripts/build_native.py。"
            )
        build_data["tag"] = builder.native_wheel_tag()
        # force_include 在打包时读取此路径，临时目录必须保留至 finalize。
        temporary = tempfile.TemporaryDirectory(prefix="doribt-native-wheel-")
        self._native_temporary = temporary
        try:
            artifact = builder.build_native(
                Path(self.root) / "src/doribt/_native_records.c", Path(temporary.name)
            )
        except BaseException:
            temporary.cleanup()
            raise
        build_data["pure_python"] = False
        build_data["infer_tag"] = False
        build_data["force_include"][str(artifact)] = f"doribt/{artifact.name}"

    def finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None:
        if hasattr(self, "_native_temporary"):
            self._native_temporary.cleanup()
