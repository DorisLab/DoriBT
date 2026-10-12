"""显式构建本地记录扩展；不会在 import 或回测时自动编译。"""

import argparse
import importlib.util
from pathlib import Path
from typing import Protocol, cast

ROOT = Path(__file__).resolve().parents[1]


class _NativeBuilder(Protocol):
    def build_native(self, source: Path, output_dir: Path) -> Path: ...


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    outputs = parser.add_mutually_exclusive_group()
    outputs.add_argument("--inplace", action="store_true", help="放入源码包，供本地开发使用")
    outputs.add_argument("--output-dir", type=Path, help="指定产物目录，默认 build/native/doribt")
    args = parser.parse_args()
    output = (
        ROOT / "src/doribt" if args.inplace else args.output_dir or ROOT / "build/native/doribt"
    )
    spec = importlib.util.spec_from_file_location(
        "_doribt_native_build", ROOT / "src/doribt/_native_build.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit("无法加载原生构建工具。")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    builder = cast(_NativeBuilder, module)
    artifact = builder.build_native(ROOT / "src/doribt/_native_records.c", output)
    print(f"原生记录扩展构建并加载成功：{artifact}")


if __name__ == "__main__":
    main()
