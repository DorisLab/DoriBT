# 可选原生记录物化

这是源码构建选项。默认安装和构建仍使用纯 Python 包，不需要 C 编译器或 Python 开发头文件。
原生扩展只优化内部列式结果到完整审计记录的转换；返回的订单、意图、成交、税务批次仍是原有
完整、立即创建的 dataclass 和 tuple，不改变公共 API，不推迟到首次访问时才创建。
当前加速入口是符合条件的 Numba 预计算执行路径；仅安装扩展不会改变 Python 后端的执行路径。

物化过程对空表直接返回空 tuple；稀疏记录只读取实际需要的日期和时间戳，
密集记录在同次物化中共享时间轴查找数组。全部非空记录仍在 `Backtest.run` 返回前创建完成，
这些优化不减少账本字段或把构造推迟到结果访问时。

Python 记录工厂在内置记录类型的 `__init__` 或 `__new__` 被替换后遵守更新的公开构造协议，
包括构造器产生的异常。原生物化只接受使用默认分配器和生成式初始化器的内部稳定 dataclass；
类型不再满足条件时，`auto` 使用 Python 记录路径，`required` 明确失败。

## 已验证边界

- 原生构建目前仅接受 Linux x86_64、CPython 3.13—3.15、启用 GIL 的非 debug 解释器
- 使用公开稳定 C API，最低接口为 Python 3.12 的 `Py_LIMITED_API=0x030C0000`
- 可使用本机 Python 3.12—3.15 的兼容开发头文件；包支持 Python 3.13—3.15
- wheel 标为 `cp313-abi3-linux_x86_64`，不是 manylinux；不声明跨发行版、macOS、Windows、
  其他架构、free-threaded 或上述范围以外 Python 版本的原生兼容性
- 无扩展时保留纯 Python 路径；不在导入、首次回测或后续运行中自动编译、下载或安装工具

`abi3` 描述所用 ABI，并不扩大发行包的 `Requires-Python` 或已测试平台范围。
基础包在 Windows／Linux 上的支持与此原生选项的较窄范围分别适用。

## 构建与运行分别控制

| 变量 | 值 | 作用 |
| --- | --- | --- |
| `DORIBT_BUILD_NATIVE` | 未设置、`off` 或 `0` | 构建纯 Python wheel，不探测编译器 |
| `DORIBT_BUILD_NATIVE` | `required` | 必须生成并加载验证原生扩展，否则构建失败 |
| `DORIBT_NATIVE_RECORDS` | `auto`（默认） | 兼容扩展可用时使用，否则使用纯 Python 记录路径 |
| `DORIBT_NATIVE_RECORDS` | `required` | 原生能力不可用时明确报错，用于原生验证任务 |
| `DORIBT_NATIVE_RECORDS` | `off` | 即使安装原生 wheel，也使用纯 Python 记录路径 |

构建开关不会为已有安装启用原生能力。运行开关不会构建扩展；改变运行开关前后应分别运行
回测并保留各自来源记录。不同物化实现与原生二进制会反映到现有 `engine_sha256` 中。

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

`DORIBT_BUILD_NATIVE=required` 不用于可编辑安装；先完成普通可编辑安装，再显式运行开发构建命令。
失败的构建不会替换既有开发二进制，因此失败后不能把旧文件当作本次构建成功的证据。
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
`--work-dir <尚不存在的目录>`，不会覆盖已有验证目录。检查内容：

1. 向副本放入假的旧原生产物，构建 sdist 并检查二进制排除、C 源码与构建工具齐备
2. 仅从解包的 sdist 构建纯 Python 和必需原生 wheel
3. 在纯 Python 构建中强制使用不存在的编译器／头文件，证明不依赖本机编译条件
4. 检查 wheel 标签、`Root-Is-Purelib`、二进制清单及全部 `RECORD` 哈希和大小
5. 分别创建全新环境，在仓库之外用 `python -I` 导入，核验来自 wheel 的真实安装路径
6. 运行合成行情与完整记录核对，观察四类记录确实调用 C 扩展，检查原生开关改变来源摘要
7. 验证纯 wheel 拒绝必需原生运行，以及缺编译器时必需原生构建失败而不生成纯 wheel

原生 CI／性能验证必须同时要求构建时 `required` 和运行时 `required`，并单独证明扩展真实调用；
仅有绿色测试或 wheel 文件名不足以证明原生路径被覆盖。完整账本与后端检查仍须运行
[质量门禁](https://github.com/DorisLab/DoriBT/blob/main/docs/quality.md)，
此安装检查不替代功能回归或性能测量。
