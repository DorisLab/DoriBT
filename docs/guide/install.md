# 安装

支持 **Python 3.13—3.15、Windows 和 Linux**。新环境推荐 **Python 3.15**；基础包只依赖 NumPy，加速和绘图按需安装。

## 创建环境并安装

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

安装基础包并查看版本：

```sh
python -m pip install doribt
python -c "import doribt; print(doribt.__version__)"
```

本手册对应 **0.6.2**，固定版本安装命令为 `python -m pip install doribt==0.6.2`。

## 加速与图表

| 安装命令 | 用途 |
| --- | --- |
| `python -m pip install "doribt[numba]"` | Numba 加速 |
| `python -m pip install "doribt[plot]"` | Matplotlib 图表与 PNG 导出 |
| `python -m pip install "doribt[numba,plot]"` | 同时安装加速和图表 |

运行时用 `RunConfig(backend="numba")` 选择 Numba。预计算目标可进入完整编译循环，首次运行完成编译后，多次回放可复用缓存。具体用法见[预计算目标](../scheduled-execution.md)。

中文图表会选择系统中的中文字体。Windows 通常使用微软雅黑；Debian／Ubuntu 可安装 `fonts-noto-cjk`。

## Python 与依赖版本

推荐组合为 **Python 3.15.0、NumPy 2.5.4、Numba 0.68.0、llvmlite 0.50.0**，已在 Windows 11 和 WSL2 Ubuntu 24.04 实测。Python 3.13／3.14 环境可直接升级 DoriBT，安装器会选择对应的依赖范围。

| Python | NumPy 下限 | 可选 Numba 下限 |
| --- | --- | --- |
| 3.13 | 2.1 | 0.61 |
| 3.14 | 2.3.3 | 0.63 |
| 3.15 | 2.5.2 | 0.68 |

当前依赖范围为 NumPy < 3、Numba < 0.69，llvmlite 由 Numba 配对安装。支持常规 GIL 的 CPython。

Python 3.13＋NumPy 2.1.3／Numba 0.61.2，以及 Python 3.14＋NumPy 2.3.5／Numba 0.63.1 也已通过实测。[版本性能比较](../performance.md#python-版本怎么选)可帮助你选择新环境。

## 跑一次回测

[第一次回测](quickstart.md)提供一个可以独立运行的三日脚本。完整配套示例可从仓库获取：

```sh
git clone https://github.com/DorisLab/DoriBT.git
cd DoriBT
python examples/quickstart.py
python examples/research.py --plot --output my-report
```

图表命令需要 `doribt[plot]`。为每次研究使用一个新的报告目录名；完整示例保留 `examples/` 目录中的辅助模块。

Linux x86_64 的源码构建还可启用[原生扩展](../native-records.md)，进一步加快部分编译路径的记录转换。
