# 原生扩展

可选 C 扩展加快 Numba 预计算路径的记录转换，适合成交与意图记录较多的研究。
订单、意图、成交和税务批次在回测结束时完整返回，调用方式与纯 Python 包一致。
Linux x86_64 用户可从源码构建；PyPI 的基础安装使用纯 Python 包。

## 构建环境

- 原生构建目前仅接受 Linux x86_64、CPython 3.13—3.15、启用 GIL 的非 debug 解释器
- 使用公开稳定 C API，最低接口为 Python 3.12 的 `Py_LIMITED_API=0x030C0000`
- 可使用本机 Python 3.12—3.15 的兼容开发头文件；包支持 Python 3.13—3.15
- wheel 标为 `cp313-abi3-linux_x86_64`，供上述本机构建环境使用
- 无扩展时使用纯 Python 记录路径

`abi3` 是扩展的稳定 ABI 标签；基础包支持 Windows／Linux，原生构建使用上面的 Linux 环境。

## 构建与运行分别控制

| 变量 | 值 | 作用 |
| --- | --- | --- |
| `DORIBT_BUILD_NATIVE` | 未设置、`off` 或 `0` | 构建纯 Python wheel，不探测编译器 |
| `DORIBT_BUILD_NATIVE` | `required` | 必须生成并加载验证原生扩展，否则构建失败 |
| `DORIBT_NATIVE_RECORDS` | `auto`（默认） | 兼容扩展可用时使用，否则使用纯 Python 记录路径 |
| `DORIBT_NATIVE_RECORDS` | `required` | 原生能力不可用时明确报错，用于原生验证任务 |
| `DORIBT_NATIVE_RECORDS` | `off` | 即使安装原生 wheel，也使用纯 Python 记录路径 |

先用构建开关生成并安装原生 wheel，再用运行开关选择记录路径。运行来源的 `engine_sha256` 会标识相应实现与二进制。

## 构建 wheel

在仓库根目录、CPython 3.13—3.15 环境中执行：

```sh
# 默认纯 Python；即使源码树有旧 .so，也不会打入 wheel。
DORIBT_BUILD_NATIVE=off uv build

# 需要本机 C11 编译器及兼容 Python 开发头文件。
DORIBT_BUILD_NATIVE=required uv build --wheel
```

头文件默认从当前解释器的 `sysconfig` 查找。若头文件单独安装，可显式指定其目录：

```sh
DORIBT_NATIVE_INCLUDE=/path/to/python3.12/include \
  DORIBT_BUILD_NATIVE=required uv build --wheel
```

该目录须含 `Python.h`、`patchlevel.h` 和 `pyconfig.h`；不接受 debug 或 free-threaded
头文件。`CC` 可指定本机编译器命令，例如 `CC=clang`。构建器不下载头文件，不自动安装编译器，
不使用 `-march=native`，也不继承额外 `CFLAGS`／`LDFLAGS` 来改变已经验证的构建配置。
编译失败、头文件缺失、平台不受支持、API 版本不符或新进程加载失败都会使 `required` 失败。

sdist 始终只含源码、构建钩子和共享构建工具，不含本机二进制。在解包后的 sdist 中，
同样可以选择纯 Python 或 `required` 原生 wheel。原生 wheel 的二进制来自本次临时编译，
不会复用源码树残留的开发产物。

## 本地开发

```sh
# 显式构建到 build/native/doribt，默认不修改源码包。
uv run --no-sync python scripts/build_native.py

# 可编辑安装需要原生能力时，显式放入源码包。
uv run --no-sync python scripts/build_native.py --inplace

# 确认已安装／本地源码扩展可用；此处导入内部模块仅用于开发诊断。
DORIBT_NATIVE_RECORDS=required uv run --no-sync python -c \
  "from doribt.runtime.native_records import available; assert available()"
```

可编辑安装先完成普通安装，再运行上面的开发构建命令。
构建失败时保留已有开发二进制，错误通过构建命令报告。
开发产物已被版本控制和发行打包规则排除。要检查纯 Python 路径，使用运行时 `off`，
或从本次生成的纯 Python wheel 建立独立环境。

## 隔离安装验证

```sh
# 如需指定头文件，先设置 DORIBT_NATIVE_INCLUDE。
uv run --no-sync python scripts/check_native_package.py \
  --report .quality/native-packaging.json
```

此检查要求已安装开发依赖、`numba` extra 与 `uv`；已有完整依赖缓存时可加 `--offline`。
纯 Python 安装检查只安装 NumPy；原生执行验证另装与当前环境同版本的 Numba／llvmlite。
默认在临时目录中验证后清理；若需要保留 wheel 与独立安装供进一步复核，可加
`--work-dir <尚不存在的目录>`，不会覆盖已有验证目录。该命令从 sdist 重建纯 Python／原生 wheel，在独立环境中检查安装、文件哈希和完整回测结果，并验证 C 扩展的实际调用。

完整开发检查见[质量门禁](https://github.com/DorisLab/DoriBT/blob/main/docs/quality.md)。
