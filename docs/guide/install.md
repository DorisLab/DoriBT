# 安装 DoriBT：Python、Numba 与图表

支持 **CPython 3.13、3.14、3.15**，适用于 Windows 和 Linux。建议使用独立虚拟环境。
新建 DoriBT 环境建议 **Python 3.15.0＋NumPy 2.5.4＋Numba 0.68.0**；llvmlite 对应 0.50.0。
这组依赖已在 Windows 11 和 WSL2 Ubuntu 24.04 完成引擎、图表及安装包验证，同输入人工面板
的完整结果也与 3.13／3.14 一致。Python 3.15 在本机测量中最快，具体范围见[版本比较](../performance.md#python-版本怎么选)。

已有研究环境可继续使用 Python 3.13，单独升级 DoriBT 即可；需要保留 Numba 0.63 的环境可选
Python 3.14.8。其他研究依赖不在上述兼容结论内，升级解释器时新建环境并复核冻结结果，不覆盖旧环境。

```sh
python --version
python -m venv .venv
```

Windows PowerShell 激活环境：

```powershell
.venv\Scripts\Activate.ps1
```

Linux：

```sh
source .venv/bin/activate
```

安装并确认版本：

```sh
python -m pip install doribt
python -c "import doribt; print(doribt.__version__)"
```

若需要复现本手册的发行版本，可安装 `doribt==0.6.2`。

依赖按解释器选择兼容范围，安装器不会要求所有用户使用同一套最新版本：

| Python | NumPy 下限 | 可选 Numba 下限 |
| --- | --- | --- |
| 3.13 | 2.1 | 0.61 |
| 3.14 | 2.3.3 | 0.63 |
| 3.15 | 2.5.2 | 0.68 |

NumPy 上限为 3，Numba 上限为 0.69（均不含）；llvmlite 由 Numba 选择对应版本。
基础安装只依赖 NumPy。Numba 0.68 搭配 llvmlite 0.50；已有 NumPy 2.4.4 环境仍可用于 Python 3.13／3.14。
这里指启用 GIL 的常规 CPython，未声明 free-threaded、PyPy 或 Python 3.16 兼容。

## 可选功能

| 安装命令 | 用途 |
| --- | --- |
| `python -m pip install "doribt[plot]"` | Matplotlib 图表和 PNG 导出 |
| `python -m pip install "doribt[numba]"` | Numba 执行后端 |
| `python -m pip install "doribt[numba,plot]"` | 同时使用加速和图表 |

安装 Numba 后，仍需在 `RunConfig(backend="numba")` 中选择它。首次运行有编译开销；任意 Python 策略回调不会整体转成机器码。详见[预计算与性能](../scheduled-execution.md)。

源码开发还提供[可选原生记录物化](../native-records.md)，目前仅验证 Linux x86_64 的
CPython 3.13—3.15 GIL 构建。普通安装无需编译器；原生构建与运行开关须分别选择。

中文图表会选择系统中的中文字体。Windows 通常可以使用微软雅黑；Linux 可安装 Noto CJK 字体（Debian／Ubuntu 包名 `fonts-noto-cjk`）。缺少中文字体时，内置图表标题回退为英文，自定义基准名称保持原文。

## 运行完整示例

[第一次回测](quickstart.md)是单文件脚本，不需要克隆仓库。要运行本手册的全套示例，获取仓库中的配套脚本：

```sh
git clone https://github.com/DorisLab/DoriBT.git
cd DoriBT
python examples/quickstart.py
python examples/research.py --plot --output my-report
```

上面的图表命令需要先安装 `doribt[plot]`，`my-report` 必须不存在。示例可能导入同目录的辅助模块，运行全套示例时保留完整 `examples/` 目录。

main 分支的示例和本手册统一使用 `RunConfig`；当前发行包支持这些接口。
